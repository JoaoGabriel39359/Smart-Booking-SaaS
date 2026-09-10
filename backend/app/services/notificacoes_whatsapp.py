import os
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import MensagemWhatsApp
from app.services.whatsapp import ResultadoEnvio, enviar_template_whatsapp, normalizar_telefone


TEMPLATES_PADRAO = {
    "lembrete_1h": ("lembrete_aula_1h_v1", "en_US"),
    "lembrete_24h": ("lembrete_aula_24h_v1", "pt_BR"),
    "link_portal": ("link_portal_aluno_v1", "pt_BR"),
    "aula_agendada": ("aula_agendada_v1", "pt_BR"),
    "aula_reagendada": ("aula_reagendada_v1", "pt_BR"),
    "aula_cancelada": ("aula_cancelada_v1", "pt_BR"),
    "cancelamento_professor": ("cancelamento_professor_v1", "pt_BR"),
    "credito_vencendo": ("credito_reposicao_vencendo_v1", "pt_BR"),
    "lembrete_breve": ("lembrete_aula_breve_v1", "pt_BR"),
}


def configuracao_template(tipo: str) -> tuple[str, str]:
    if tipo not in TEMPLATES_PADRAO:
        raise ValueError(f"Tipo de notificação WhatsApp desconhecido: {tipo}")
    nome_padrao, idioma_padrao = TEMPLATES_PADRAO[tipo]
    sufixo = tipo.upper()
    nome = os.getenv(f"YCLOUD_TEMPLATE_{sufixo}", nome_padrao).strip() or nome_padrao
    idioma = os.getenv(f"YCLOUD_TEMPLATE_{sufixo}_LANGUAGE", idioma_padrao).strip() or idioma_padrao
    return nome, idioma


def _resultado_existente(registro: MensagemWhatsApp) -> ResultadoEnvio:
    return ResultadoEnvio(
        aceito=registro.status in {"accepted", "sent", "delivered", "read"},
        provider=registro.provider,
        status=registro.status,
        id_mensagem=registro.provider_message_id,
        wamid=registro.wamid,
        erro_codigo=registro.erro_codigo,
        erro_mensagem=registro.erro_mensagem,
    )


def enviar_notificacao_rastreada(
    db: Session,
    *,
    external_id: str,
    numero: str,
    tipo: str,
    parametros: Iterable[str],
    mensagem_fallback: str,
    aluno_id: Optional[int] = None,
    aula_id: Optional[int] = None,
) -> ResultadoEnvio:
    """Reserva um ID antes do envio para que reexecuções não dupliquem mensagens."""
    existente = db.query(MensagemWhatsApp).filter(
        MensagemWhatsApp.external_id == external_id
    ).with_for_update().first()
    template_nome, template_idioma = configuracao_template(tipo)

    if existente:
        # Uma rejeição síncrona é comprovadamente segura para repetir. Falha de
        # entrega após "accepted" e falha de rede continuam bloqueadas para evitar
        # que uma resposta perdida gere duas mensagens para o aluno.
        max_tentativas = max(int(os.getenv("YCLOUD_MAX_SYNC_RETRIES", "3")), 1)
        if (
            existente.status == "falhou"
            and existente.aceito_em is None
            and existente.tentativas < max_tentativas
        ):
            registro = existente
            registro.status = "processando"
            registro.tentativas += 1
            registro.template_nome = template_nome
            registro.erro_codigo = None
            registro.erro_mensagem = None
            registro.falhou_em = None
            db.commit()
        else:
            return _resultado_existente(existente)
    else:
        registro = MensagemWhatsApp(
            external_id=external_id,
            provider="pendente",
            tipo=tipo,
            template_nome=template_nome,
            destinatario=normalizar_telefone(numero),
            aluno_id=aluno_id,
            aula_id=aula_id,
            status="processando",
            tentativas=1,
        )
        db.add(registro)
        try:
            # A reserva precisa existir antes da chamada de rede. Se outro worker
            # tentar o mesmo external_id, o índice único impede o segundo disparo.
            db.commit()
            db.refresh(registro)
        except IntegrityError:
            db.rollback()
            existente = db.query(MensagemWhatsApp).filter(
                MensagemWhatsApp.external_id == external_id
            ).first()
            if existente:
                return _resultado_existente(existente)
            raise

    try:
        resultado = enviar_template_whatsapp(
            numero,
            template_nome,
            parametros,
            template_idioma=template_idioma,
            external_id=external_id,
            mensagem_fallback=mensagem_fallback,
        )
    except Exception as exc:
        resultado = ResultadoEnvio(
            aceito=False,
            provider="desconhecido",
            status="desconhecido",
            erro_codigo="ERRO_INTERNO_ENVIO",
            erro_mensagem=str(exc),
        )
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    registro.provider = resultado.provider
    registro.provider_message_id = resultado.id_mensagem
    registro.wamid = resultado.wamid
    registro.status = resultado.status
    registro.erro_codigo = resultado.erro_codigo
    registro.erro_mensagem = resultado.erro_mensagem
    registro.atualizado_em = agora
    if resultado.aceito:
        registro.aceito_em = agora
        if resultado.status in {"sent", "delivered", "read"}:
            registro.enviado_em = agora
        if resultado.status in {"delivered", "read"}:
            registro.entregue_em = agora
        if resultado.status == "read":
            registro.lido_em = agora
    elif resultado.status == "falhou":
        registro.falhou_em = agora
    db.commit()
    return resultado


def enviar_notificacao_background(**kwargs) -> None:
    db = SessionLocal()
    try:
        resultado = enviar_notificacao_rastreada(db, **kwargs)
        if not resultado:
            print(
                f"❌ Notificação WhatsApp {kwargs.get('external_id')} falhou: "
                f"{resultado.erro_codigo} - {resultado.erro_mensagem}"
            )
    except Exception as exc:
        db.rollback()
        print(f"❌ Erro ao registrar notificação WhatsApp: {exc}")
    finally:
        db.close()


_STATUS_VALIDOS = {"accepted", "sent", "delivered", "read", "failed"}
_STATUS_ORDEM = {"processando": 0, "desconhecido": 0, "accepted": 1, "sent": 2, "failed": 2, "delivered": 3, "read": 4}


def atualizar_status_por_webhook(db: Session, dados: dict) -> Optional[MensagemWhatsApp]:
    """Aplica um status assíncrono sem regredir uma entrega já confirmada."""
    provider_id = dados.get("id")
    external_id = dados.get("externalId")
    wamid = dados.get("wamid")
    registro = None
    if provider_id:
        registro = db.query(MensagemWhatsApp).filter(
            MensagemWhatsApp.provider_message_id == str(provider_id)
        ).first()
    if not registro and external_id:
        registro = db.query(MensagemWhatsApp).filter(
            MensagemWhatsApp.external_id == str(external_id)
        ).first()
    if not registro and wamid:
        registro = db.query(MensagemWhatsApp).filter(
            MensagemWhatsApp.wamid == str(wamid)
        ).first()
    if not registro:
        db.commit()
        return None

    novo_status = str(dados.get("status") or "").lower()
    if novo_status not in _STATUS_VALIDOS:
        db.commit()
        return registro

    atual = registro.status or "processando"
    deve_atualizar = _STATUS_ORDEM.get(novo_status, 0) >= _STATUS_ORDEM.get(atual, 0)
    if atual in {"delivered", "read"} and novo_status == "failed":
        deve_atualizar = False
    if atual == "failed" and novo_status == "sent":
        deve_atualizar = False
    if atual == "read" and novo_status == "delivered":
        deve_atualizar = False

    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    registro.provider_message_id = str(provider_id) if provider_id else registro.provider_message_id
    registro.wamid = str(wamid) if wamid else registro.wamid
    registro.atualizado_em = agora
    if deve_atualizar:
        registro.status = novo_status
        if novo_status == "accepted":
            registro.aceito_em = registro.aceito_em or agora
        elif novo_status == "sent":
            registro.enviado_em = agora
        elif novo_status == "delivered":
            registro.entregue_em = agora
            registro.falhou_em = None
            registro.erro_codigo = None
            registro.erro_mensagem = None
        elif novo_status == "read":
            registro.entregue_em = registro.entregue_em or agora
            registro.lido_em = agora
            registro.falhou_em = None
            registro.erro_codigo = None
            registro.erro_mensagem = None
        elif novo_status == "failed":
            registro.falhou_em = agora
            registro.erro_codigo = str(dados.get("errorCode") or "FALHA_ENTREGA")
            registro.erro_mensagem = str(
                dados.get("errorMessage") or "A YCloud informou falha na entrega."
            )[:1000]
    db.commit()
    return registro
