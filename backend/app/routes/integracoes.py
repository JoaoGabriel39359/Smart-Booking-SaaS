from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import verificar_token
from app.database import get_db
from app.models import MensagemWhatsApp
from app.services.notificacoes_whatsapp import TEMPLATES_PADRAO, configuracao_template
from app.services.whatsapp import configuracao_whatsapp_publica


router = APIRouter(prefix="/integracoes", tags=["integrações"])


def _mascarar_telefone(numero: str) -> str:
    if len(numero or "") <= 4:
        return "****"
    return f"***{numero[-4:]}"


@router.get("/whatsapp/status")
def status_whatsapp(
    limite: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    del usuario
    totais = {
        status: total
        for status, total in db.query(
            MensagemWhatsApp.status,
            func.count(MensagemWhatsApp.id),
        ).group_by(MensagemWhatsApp.status).all()
    }
    recentes = db.query(MensagemWhatsApp).order_by(
        MensagemWhatsApp.criado_em.desc()
    ).limit(limite).all()
    return {
        **configuracao_whatsapp_publica(),
        "webhook": "/webhook/ycloud",
        "totais": totais,
        "templates": {
            tipo: {"nome": configuracao_template(tipo)[0], "idioma": configuracao_template(tipo)[1]}
            for tipo in TEMPLATES_PADRAO
        },
        "mensagens_recentes": [
            {
                "external_id": item.external_id,
                "tipo": item.tipo,
                "destinatario": _mascarar_telefone(item.destinatario),
                "status": item.status,
                "provider": item.provider,
                "erro_codigo": item.erro_codigo,
                "erro_mensagem": item.erro_mensagem,
                "criado_em": item.criado_em,
                "atualizado_em": item.atualizado_em,
                "entregue_em": item.entregue_em,
                "lido_em": item.lido_em,
            }
            for item in recentes
        ],
    }


@router.post("/whatsapp/destravar")
def destravar_mensagens_whatsapp(
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    del usuario
    presas = db.query(MensagemWhatsApp).filter(
        MensagemWhatsApp.aceito_em.is_(None),
        MensagemWhatsApp.status.in_(["falhou", "processando", "desconhecido"]),
    ).all()
    count = 0
    for item in presas:
        item.status = "processando"
        item.tentativas = 0
        item.erro_codigo = None
        item.erro_mensagem = None
        count += 1
    db.commit()
    return {"status": "sucesso", "mensagens_destravadas": count}

