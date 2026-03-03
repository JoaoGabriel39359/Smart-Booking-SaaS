from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db, SessionLocal 
from app.models import Aula
from app.services.whatsapp import enviar_whatsapp

router = APIRouter(prefix="/jobs", tags=["automação"])

# --- 1. A FUNÇÃO QUE O SISTEMA JÁ CONHECE ---
def verificar_lembretes(db: Session):
    """
    Mantivemos o nome original. Esta função faz a lógica.
    """
    agora = datetime.now()
    janela_20min = agora + timedelta(minutes=25)

    aulas = db.query(Aula).filter(
        Aula.status == "marcada",
        Aula.lembrete_enviado == False,
        Aula.data_inicio >= agora,
        Aula.data_inicio <= janela_20min
    ).all()

    enviados = 0
    for aula in aulas:
        try:
            nome_aluno = aula.aluno.nome if aula.aluno else "Aluno"
            horario = aula.data_inicio.strftime('%H:%M')
            
            msg = f"Ei {nome_aluno}! 👋\n\nSua aula começa em *20 minutos* ({horario}). Já está pronto(a)?"
            
            sucesso = enviar_whatsapp(aula.aluno.telefone, msg)
            
            if sucesso:
                aula.lembrete_enviado = True
                db.commit()
                enviados += 1
                print(f"✅ Lembrete enviado para {nome_aluno}")
        except Exception as e:
            db.rollback()
            print(f"Erro ao processar lembrete da aula {aula.id}: {e}")
    
    return enviados

# --- 2. ROTA PARA O NAVEGADOR ---
@router.get("/verificar-lembretes")
def rota_verificar_lembretes(db: Session = Depends(get_db)):
    total = verificar_lembretes(db)
    return {"status": "sucesso", "lembretes_enviados": total}

# --- 3. FUNÇÃO PARA O SCHEDULER (O VIGIA AUTOMÁTICO) ---
def verificar_lembretes_background():
    """
    Esta função abre o banco sozinha para o agendador não travar.
    """
    db = SessionLocal()
    try:
        verificar_lembretes(db)
    finally:
        db.close()