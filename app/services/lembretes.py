from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import Aula
from app.services.whatsapp import enviar_whatsapp  # vamos criar depois

def verificar_lembretes():
    db = SessionLocal()

    agora = datetime.now()
    limite = agora + timedelta(minutes=20)

    aulas = db.query(Aula).filter(
        Aula.status == "marcada",
        Aula.lembrete_enviado == False,
        Aula.data_inicio >= agora,
        Aula.data_inicio <= limite
    ).all()

    for aula in aulas:
        enviar_whatsapp(
            numero=aula.aluno.telefone,
            mensagem=f"Lembrete: sua aula começa às {aula.data_inicio.strftime('%H:%M')}"
        )

        aula.lembrete_enviado = True

    db.commit()
    db.close()
