import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.getcwd())
from app.database import SessionLocal
from app.models import Aula
from app.services.whatsapp import enviar_whatsapp

def enviar_lembretes_20min():
    db = SessionLocal()
    agora = datetime.now()
    
    # Janela de 10 minutos para garantir que não perderemos ninguém
    janela_inicio = agora + timedelta(minutes=15)
    janela_fim = agora + timedelta(minutes=25)

    proximas_aulas = db.query(Aula).filter(
        Aula.data_inicio >= janela_inicio,
        Aula.data_inicio <= janela_fim,
        Aula.status == 'marcada',
        Aula.lembrete_enviado == False
    ).all()

    if not proximas_aulas:
        print(f"[{agora.strftime('%H:%M')}] Nenhuma aula nos próximos 20 min.")

    for aula in proximas_aulas:
        msg = (
            f"Ei {aula.aluno.nome}, sua aula começa em 20 minutos! 🧘‍♂️\n"
            f"Já estamos te esperando. Até logo!"
        )
        try:
            enviar_whatsapp(aula.aluno.telefone, msg)
            aula.lembrete_enviado = True # Crucial: marca para não repetir
            db.commit()
            print(f"✅ Lembrete 20min enviado para: {aula.aluno.nome}")
        except Exception as e:
            print(f"❌ Erro ao enviar lembrete para {aula.aluno.nome}: {e}")
    
    db.close()

if __name__ == "__main__":
    enviar_lembretes_20min()