import hashlib
import hmac
import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app import models
from app.core.config import BASE_URL
from app.database import get_db
from app.services.notificacoes_whatsapp import atualizar_status_por_webhook
from app.services.whatsapp import enviar_whatsapp, enviar_whatsapp_detalhado, normalizar_telefone


router = APIRouter(prefix="/webhook", tags=["Webhook"])


def verificar_assinatura_ycloud(corpo: bytes, cabecalho: str, segredo: str) -> bool:
    if not corpo or not cabecalho or not segredo:
        return False
    partes = {}
    for item in cabecalho.split(","):
        chave, separador, valor = item.strip().partition("=")
        if separador:
            partes[chave] = valor
    timestamp = partes.get("t")
    assinatura = partes.get("s")
    if not timestamp or not assinatura:
        return False
    assinado = timestamp.encode("utf-8") + b"." + corpo
    esperado = hmac.new(segredo.encode("utf-8"), assinado, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura)


def _auto_resposta_ativa() -> bool:
    return os.getenv("WHATSAPP_AUTO_REPLY_PORTAL", "false").strip().lower() in {
        "1", "true", "yes", "sim",
    }


def _buscar_aluno_por_telefone(db: Session, telefone: str):
    procurado = normalizar_telefone(telefone)
    if not procurado:
        return None
    for aluno in db.query(models.Aluno).all():
        if normalizar_telefone(aluno.telefone) == procurado:
            return aluno
    return None


def _responder_portal_ycloud(
    event_id: str,
    telefone: str,
    aluno_nome: str = "",
    token_acesso: str = "",
) -> None:
    if aluno_nome and token_acesso:
        link_portal = f"{BASE_URL}/portal/{token_acesso}"
        resposta = (
            f"Olá, *{aluno_nome}*! 😊\n\n"
            "Para agendar novas aulas, cancelar horários ou ver seus créditos de reposição, "
            "acesse seu painel exclusivo no link abaixo:\n\n"
            f"🔗 {link_portal}\n\n"
            "_Este é um atendimento automático._"
        )
    else:
        resposta = (
            "Olá! Este número não está cadastrado. Por favor, entre em contato "
            "com o professor para efetivar sua matrícula."
        )
    resultado = enviar_whatsapp_detalhado(
        telefone,
        resposta,
        external_id=f"webhook:{event_id}:resposta-portal",
    )
    if not resultado:
        print(
            f"❌ Auto-resposta do webhook {event_id} falhou: "
            f"{resultado.erro_codigo} - {resultado.erro_mensagem}"
        )


@router.post("/ycloud")
async def ycloud_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    corpo = await request.body()
    segredo = os.getenv("YCLOUD_WEBHOOK_SECRET", "").strip()
    if not segredo:
        raise HTTPException(status_code=503, detail="Webhook YCloud ainda não configurado.")
    if not verificar_assinatura_ycloud(
        corpo,
        request.headers.get("YCloud-Signature", ""),
        segredo,
    ):
        raise HTTPException(status_code=401, detail="Assinatura YCloud inválida.")

    try:
        evento = json.loads(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="JSON inválido.")

    event_id = str(evento.get("id") or "").strip()
    event_type = str(evento.get("type") or "").strip()
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Evento sem id ou type.")

    existente = db.query(models.EventoWebhookWhatsApp).filter(
        models.EventoWebhookWhatsApp.event_id == event_id
    ).first()
    if existente:
        return {"status": "ignorado", "motivo": "evento_duplicado"}

    db.add(models.EventoWebhookWhatsApp(event_id=event_id, event_type=event_type))

    if event_type == "whatsapp.message.updated":
        registro = atualizar_status_por_webhook(db, evento.get("whatsappMessage") or {})
        return {
            "status": "processado",
            "mensagem_encontrada": registro is not None,
        }

    if event_type == "whatsapp.inbound_message.received" and _auto_resposta_ativa():
        mensagem = evento.get("whatsappInboundMessage") or {}
        telefone = str(mensagem.get("from") or "")
        aluno = _buscar_aluno_por_telefone(db, telefone)
        db.commit()
        if telefone:
            background_tasks.add_task(
                _responder_portal_ycloud,
                event_id,
                telefone,
                aluno.nome if aluno else "",
                aluno.token_acesso if aluno else "",
            )
        return {"status": "processado", "auto_resposta": bool(telefone)}

    db.commit()
    return {"status": "ignorado", "motivo": "evento_sem_acao"}


@router.post("/zap")
def whatsapp_webhook_legado(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db),
):
    """Compatibilidade temporária com o antigo webhook em formato Twilio."""
    if os.getenv("WHATSAPP_LEGACY_WEBHOOK_ENABLED", "false").strip().lower() not in {
        "1", "true", "yes", "sim",
    }:
        raise HTTPException(status_code=410, detail="Webhook legado desativado.")
    del Body
    telefone_limpo = From.replace("whatsapp:", "").replace("+", "")
    aluno = _buscar_aluno_por_telefone(db, telefone_limpo)

    if not aluno:
        msg_erro = (
            "Olá! Este número não está cadastrado. Por favor, entre em contato "
            "com o professor para efetivar sua matrícula."
        )
        background_tasks.add_task(enviar_whatsapp, From, msg_erro)
        return {"status": "aluno_nao_encontrado"}

    link_portal = f"{BASE_URL}/portal/{aluno.token_acesso}"
    resposta = (
        f"Olá, *{aluno.nome}*! 😊\n\n"
        "Para agendar novas aulas, cancelar horários ou ver seus créditos de reposição, "
        "acesse seu painel exclusivo no link abaixo:\n\n"
        f"🔗 {link_portal}\n\n"
        "_Este é um atendimento automático._"
    )
    background_tasks.add_task(enviar_whatsapp, From, resposta)
    return {"status": "link_enviado"}
