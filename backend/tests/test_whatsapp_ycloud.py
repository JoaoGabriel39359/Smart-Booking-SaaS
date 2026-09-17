import hashlib
import hmac
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import requests

from app.models import Aluno, Aula, MensagemWhatsApp, StatusAula, TipoAluno
from app.routes.webhook import verificar_assinatura_ycloud
from app.services.notificacoes_whatsapp import enviar_notificacao_rastreada
from app.services.whatsapp import ResultadoEnvio, enviar_template_whatsapp


class RespostaFake:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


def _resultado(aceito=True, status="accepted", message_id="msg_123"):
    return ResultadoEnvio(
        aceito=aceito,
        provider="ycloud",
        status=status,
        id_mensagem=message_id,
        erro_codigo=None if aceito else "400",
        erro_mensagem=None if aceito else "Rejeitado",
    )


def _assinatura(corpo: bytes, segredo: str, timestamp="1760000000") -> str:
    assinatura = hmac.new(
        segredo.encode(),
        timestamp.encode() + b"." + corpo,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},s={assinatura}"


def test_ycloud_envia_template_com_payload_correto(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ycloud")
    monkeypatch.setenv("YCLOUD_API_KEY", "chave-teste")
    monkeypatch.setenv("YCLOUD_PHONE_NUMBER", "5511999999999")
    post = MagicMock(return_value=RespostaFake(data={"id": "ycloud-1", "status": "accepted"}))
    monkeypatch.setattr("app.services.whatsapp.requests.post", post)

    resultado = enviar_template_whatsapp(
        "(11) 98888-7777",
        "lembrete_aula_1h_v1",
        ["Ana", "13:00"],
        template_idioma="en_US",
        external_id="aula:10:lembrete-1h",
        mensagem_fallback="fallback",
    )

    assert resultado.aceito is True
    assert resultado.id_mensagem == "ycloud-1"
    chamada = post.call_args
    assert chamada.args[0] == "https://api.ycloud.com/v2/whatsapp/messages"
    assert chamada.kwargs["headers"]["X-API-Key"] == "chave-teste"
    payload = chamada.kwargs["json"]
    assert payload["from"] == "+5511999999999"
    assert payload["to"] == "+5511988887777"
    assert payload["externalId"] == "aula:10:lembrete-1h"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "lembrete_aula_1h_v1"
    assert payload["template"]["language"]["code"] == "en_US"
    assert [
        item["text"]
        for item in payload["template"]["components"][0]["parameters"]
    ] == ["Ana", "13:00"]
    assert payload["filterUnsubscribed"] is True
    assert payload["filterBlocked"] is True


def test_ycloud_timeout_fica_desconhecido_sem_confirmar(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ycloud")
    monkeypatch.setenv("YCLOUD_API_KEY", "chave-teste")
    monkeypatch.setenv("YCLOUD_PHONE_NUMBER", "+5511999999999")
    monkeypatch.setattr(
        "app.services.whatsapp.requests.post",
        MagicMock(side_effect=requests.Timeout("tempo excedido")),
    )

    resultado = enviar_template_whatsapp(
        "5511988887777",
        "lembrete_aula_1h_v1",
        ["Ana", "13:00"],
        external_id="aula:11:lembrete-1h",
    )

    assert resultado.aceito is False
    assert resultado.status == "desconhecido"
    assert resultado.erro_codigo == "ERRO_DE_REDE"


def test_rastreamento_impede_reenvio_do_mesmo_external_id(db_session, monkeypatch):
    enviar = MagicMock(return_value=_resultado())
    monkeypatch.setattr(
        "app.services.notificacoes_whatsapp.enviar_template_whatsapp",
        enviar,
    )
    kwargs = {
        "external_id": "aula:20:lembrete-1h",
        "numero": "5511988887777",
        "tipo": "lembrete_1h",
        "parametros": ["Ana", "13:00"],
        "mensagem_fallback": "Lembrete",
    }

    primeiro = enviar_notificacao_rastreada(db_session, **kwargs)
    segundo = enviar_notificacao_rastreada(db_session, **kwargs)

    assert primeiro.aceito is True
    assert segundo.aceito is True
    assert enviar.call_count == 1
    assert db_session.query(MensagemWhatsApp).count() == 1


def test_rejeicao_sincrona_pode_ser_retentada(db_session, monkeypatch):
    enviar = MagicMock(side_effect=[_resultado(False, "falhou", None), _resultado()])
    monkeypatch.setattr(
        "app.services.notificacoes_whatsapp.enviar_template_whatsapp",
        enviar,
    )
    kwargs = {
        "external_id": "aula:21:lembrete-1h",
        "numero": "5511988887777",
        "tipo": "lembrete_1h",
        "parametros": ["Ana", "13:00"],
        "mensagem_fallback": "Lembrete",
    }

    assert not enviar_notificacao_rastreada(db_session, **kwargs)
    assert enviar_notificacao_rastreada(db_session, **kwargs)

    registro = db_session.query(MensagemWhatsApp).one()
    assert registro.tentativas == 2
    assert registro.status == "accepted"
    assert enviar.call_count == 2


def test_estado_ambiguo_nao_e_reenviado(db_session, monkeypatch):
    desconhecido = ResultadoEnvio(
        aceito=False,
        provider="ycloud",
        status="desconhecido",
        erro_codigo="ERRO_DE_REDE",
        erro_mensagem="timeout",
    )
    enviar = MagicMock(return_value=desconhecido)
    monkeypatch.setattr(
        "app.services.notificacoes_whatsapp.enviar_template_whatsapp",
        enviar,
    )
    kwargs = {
        "external_id": "aula:22:lembrete-1h",
        "numero": "5511988887777",
        "tipo": "lembrete_1h",
        "parametros": ["Ana", "13:00"],
        "mensagem_fallback": "Lembrete",
    }

    assert not enviar_notificacao_rastreada(db_session, **kwargs)
    assert not enviar_notificacao_rastreada(db_session, **kwargs)
    assert enviar.call_count == 1


def test_assinatura_ycloud_valida_corpo_exato():
    corpo = b'{"id":"evt_1"}'
    cabecalho = _assinatura(corpo, "segredo")

    assert verificar_assinatura_ycloud(corpo, cabecalho, "segredo") is True
    assert verificar_assinatura_ycloud(corpo + b" ", cabecalho, "segredo") is False
    assert verificar_assinatura_ycloud(corpo, "t=1,s=invalida", "segredo") is False


def test_webhook_atualiza_entrega_e_ignora_evento_repetido(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "segredo-webhook")
    registro = MensagemWhatsApp(
        external_id="aula:30:lembrete-1h",
        provider="ycloud",
        provider_message_id="ycloud-30",
        tipo="lembrete_1h",
        template_nome="lembrete_aula_1h_v1",
        destinatario="5511988887777",
        status="accepted",
        tentativas=1,
    )
    db_session.add(registro)
    db_session.commit()

    evento = {
        "id": "evt_entregue_30",
        "type": "whatsapp.message.updated",
        "apiVersion": "v2",
        "whatsappMessage": {
            "id": "ycloud-30",
            "wamid": "wamid.30",
            "externalId": "aula:30:lembrete-1h",
            "status": "delivered",
        },
    }
    corpo = json.dumps(evento, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "YCloud-Signature": _assinatura(corpo, "segredo-webhook"),
    }

    primeira = client.post("/webhook/ycloud", content=corpo, headers=headers)
    segunda = client.post("/webhook/ycloud", content=corpo, headers=headers)

    assert primeira.status_code == 200
    assert primeira.json()["mensagem_encontrada"] is True
    assert segunda.json() == {"status": "ignorado", "motivo": "evento_duplicado"}
    db_session.refresh(registro)
    assert registro.status == "delivered"
    assert registro.entregue_em is not None
    assert registro.wamid == "wamid.30"


def test_webhook_nao_regride_entregue_para_falhou(client, db_session, monkeypatch):
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "segredo-webhook")
    registro = MensagemWhatsApp(
        external_id="aula:31:lembrete-1h",
        provider="ycloud",
        provider_message_id="ycloud-31",
        tipo="lembrete_1h",
        destinatario="5511988887777",
        status="delivered",
        tentativas=1,
    )
    db_session.add(registro)
    db_session.commit()
    evento = {
        "id": "evt_falha_atrasada_31",
        "type": "whatsapp.message.updated",
        "whatsappMessage": {
            "id": "ycloud-31",
            "status": "failed",
            "errorCode": "131000",
            "errorMessage": "evento fora de ordem",
        },
    }
    corpo = json.dumps(evento, separators=(",", ":")).encode()

    resposta = client.post(
        "/webhook/ycloud",
        content=corpo,
        headers={
            "Content-Type": "application/json",
            "YCloud-Signature": _assinatura(corpo, "segredo-webhook"),
        },
    )

    assert resposta.status_code == 200
    db_session.refresh(registro)
    assert registro.status == "delivered"


def test_webhook_rejeita_assinatura_invalida(client, monkeypatch):
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "segredo-webhook")
    resposta = client.post(
        "/webhook/ycloud",
        content=b'{"id":"evt_invalido","type":"whatsapp.message.updated"}',
        headers={"YCloud-Signature": "t=1,s=invalida"},
    )

    assert resposta.status_code == 401



def test_job_de_lembrete_nao_dispara_duas_vezes(
    db_session, monkeypatch
):
    from app.services import lembretes
    from app.services.notificacoes_whatsapp import enviar_notificacao_rastreada as envio_real

    agora = datetime(2026, 9, 10, 10, 0, 0)
    aluno = Aluno(
        nome="Ana",
        sobrenome="Teste",
        telefone="5511988887777",
        tipo=TipoAluno.VIP,
    )
    aula = Aula(
        aluno=aluno,
        data_inicio=agora + timedelta(minutes=62),
        data_fim=agora + timedelta(minutes=122),
        status=StatusAula.marcada,
        lembrete_enviado=False,
    )
    db_session.add_all([aluno, aula])
    db_session.commit()
    monkeypatch.setattr(lembretes, "agora_br", lambda: agora)
    monkeypatch.setattr(lembretes, "enviar_notificacao_rastreada", envio_real)

    primeiro = lembretes.verificar_lembretes(db_session)
    segundo = lembretes.verificar_lembretes(db_session)

    assert primeiro == 1
    assert segundo == 0
    db_session.refresh(aula)
    assert aula.lembrete_enviado is True
    assert db_session.query(MensagemWhatsApp).filter(
        MensagemWhatsApp.external_id == f"aula:{aula.id}:lembrete-1h"
    ).count() == 1



def test_job_de_lembrete_respeita_pausa_de_migracao(db_session, monkeypatch):
    from app.services import lembretes

    agora = datetime(2026, 9, 10, 10, 0, 0)
    aluno = Aluno(
        nome="Ana",
        sobrenome="Teste",
        telefone="5511988887777",
        tipo=TipoAluno.VIP,
    )
    aula = Aula(
        aluno=aluno,
        data_inicio=agora + timedelta(minutes=62),
        data_fim=agora + timedelta(minutes=122),
        status=StatusAula.marcada,
        lembrete_enviado=False,
    )
    db_session.add_all([aluno, aula])
    db_session.commit()
    monkeypatch.setenv("WHATSAPP_REMINDERS_ENABLED", "false")
    monkeypatch.setattr(lembretes, "agora_br", lambda: agora)
    enviar = MagicMock()
    monkeypatch.setattr(lembretes, "enviar_notificacao_rastreada", enviar)

    assert lembretes.verificar_lembretes(db_session) == 0
    enviar.assert_not_called()
    db_session.refresh(aula)
    assert aula.lembrete_enviado is False
    assert db_session.query(MensagemWhatsApp).count() == 0


def test_recupera_registro_preso_em_processando(db_session, monkeypatch):
    enviar = MagicMock(return_value=_resultado())
    monkeypatch.setattr(
        "app.services.notificacoes_whatsapp.enviar_template_whatsapp",
        enviar,
    )
    preso = MensagemWhatsApp(
        external_id="aula:99:lembrete-1h",
        provider="pendente",
        tipo="lembrete_1h",
        destinatario="5511988887777",
        status="processando",
        criado_em=datetime.now() - timedelta(minutes=5),
        tentativas=1,
    )
    db_session.add(preso)
    db_session.commit()

    resultado = enviar_notificacao_rastreada(
        db_session,
        external_id="aula:99:lembrete-1h",
        numero="5511988887777",
        tipo="lembrete_1h",
        parametros=["Ana", "13:00"],
        mensagem_fallback="Lembrete",
    )

    assert resultado.aceito is True
    db_session.refresh(preso)
    assert preso.status == "accepted"
    assert preso.tentativas == 2

