from fastapi import APIRouter, Form, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.services.whatsapp import enviar_whatsapp 
from datetime import datetime

router = APIRouter(prefix="/webhook", tags=["Webhook"])

@router.post("/zap")
def whatsapp_webhook(background_tasks: BackgroundTasks, From: str = Form(...), Body: str = Form(...), db: Session = Depends(get_db)):
    # 1. Tratar o número (Twilio manda 'whatsapp:+5511999999999')
    telefone_limpo = From.replace("whatsapp:", "").replace("+", "")
    mensagem_usuario = Body.lower().strip()

    # 2. Buscar aluno no banco
    aluno = db.query(models.Aluno).filter(models.Aluno.telefone.contains(telefone_limpo)).first()

    if not aluno:
        msg_erro = "Olá! Este número não está cadastrado. Por favor, entre em contato com o professor para efetivar sua matrícula."
        background_tasks.add_task(enviar_whatsapp, From, msg_erro)
        return {"status": "aluno_nao_encontrado"}

    # 3. Lógica de resposta única: Enviar o Link do Portal
    # Aqui você usará o IP ou domínio onde seu sistema está rodando
    link_portal = f"http://seu-ip-ou-dominio:8000/portal/{aluno.id}"
    
    resposta = (
        f"Olá, *{aluno.nome}*! 😊\n\n"
        f"Para agendar novas aulas, cancelar horários ou ver seus créditos de reposição, "
        f"acesse seu painel exclusivo no link abaixo:\n\n"
        f"🔗 {link_portal}\n\n"
        f"_Este é um atendimento automático._"
    )

    background_tasks.add_task(enviar_whatsapp, From, resposta)
    
    return {"status": "link_enviado"}