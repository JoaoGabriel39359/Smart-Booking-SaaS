import os
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import Aula, StatusAula
from app.services.whatsapp import enviar_whatsapp
from app.core.config import agora_br

def enviar_lembretes_20min():
    db = SessionLocal()
    try:
        agora = agora_br()
        
        janela_inicio = agora + timedelta(minutes=15)
        janela_fim = agora + timedelta(minutes=25)

        proximas_aulas = db.query(Aula).filter(
            Aula.data_inicio >= janela_inicio,
            Aula.data_inicio <= janela_fim,
            Aula.status.in_(["marcada", StatusAula.marcada]),
            Aula.lembrete_enviado == False     
        ).all()

        if not proximas_aulas:
            print(f"[{agora.strftime('%H:%M')}] Nenhuma aula nos próximos 20 min.")

        for aula in proximas_aulas:
            if not aula.aluno:
                continue
            msg = (
                f"Ei {aula.aluno.nome}, sua aula começa em 20 minutos! 🧘‍♂️\n"
                f"Já estamos te esperando. Até logo!"
            )
            try:
                enviar_whatsapp(aula.aluno.telefone, msg)
                aula.lembrete_enviado = True
                db.commit()
                print(f"✅ Lembrete 20min enviado para: {aula.aluno.nome}")
            except Exception as e:
                print(f"❌ Erro ao enviar lembrete para {aula.aluno.nome}: {e}")
    except Exception as e:
        db.rollback()
        print(f"❌ Erro no script de lembrete imediato: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    enviar_lembretes_20min()
