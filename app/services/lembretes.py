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
            
            msg = (
                    f"Hello {nome_aluno}! 👋\n\n"
                    f"Passing by to let you know that your class starts in *20 minutes* ({horario}).\n"
                    f"Are you ready? ⏰📚"
                )
            
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
    db = SessionLocal()
    try:
        agora = datetime.now()
        # Procura aulas em exatas 10 horas
        check_10h = agora + timedelta(hours=10)
        
        aulas_10h = db.query(Aula).filter(
            Aula.data_inicio >= check_10h,
            Aula.data_inicio <= check_10h + timedelta(minutes=1),
            Aula.status == "marcada"
        ).all()

        for aula in aulas_10h:
            aluno = aula.aluno
            if aluno.tipo == "VIP":
                msg = (
                    f"Olá {aluno.nome}, passando para confirmar sua aula em 10 horas! 🎓\n"
                    f"Horário: *{aula.data_inicio.strftime('%H:%M')}*\n\n"
                    f"Lembrando: você pode reagendar pelo portal com até 3h de antecedência."
                )
                enviar_whatsapp(aluno.telefone, msg)
    finally:
        db.close()