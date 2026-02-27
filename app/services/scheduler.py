from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import Aula, Aluno
from app.services.whatsapp import enviar_whatsapp
from apscheduler.schedulers.background import BackgroundScheduler

def verificar_lembretes_20min():
    db = SessionLocal()
    try:
        # 1. Definimos a janela de busca: aulas que começam daqui a 20 minutos
        # Usamos uma margem de 1 minuto para garantir que o job pegue a aula
        agora = datetime.now()
        alvo_inicio = agora + timedelta(minutes=20)
        alvo_fim = alvo_inicio + timedelta(minutes=1)

        # 2. Buscamos aulas 'marcadas' que iniciam nessa janela
        aulas = db.query(Aula).filter(
            Aula.data_inicio >= alvo_inicio,
            Aula.data_inicio < alvo_fim,
            Aula.status == "marcada"
        ).all()

        for aula in aulas:
            # O relacionamento 'aula.aluno' deve estar configurado no seu model Aula
            aluno = db.query(Aluno).filter(Aluno.id == aula.aluno_id).first()
            
            if aluno:
                horario_formatado = aula.data_inicio.strftime('%H:%M')
                mensagem = (
                    f"Ei {aluno.nome}! 👋\n\n"
                    f"Passando para avisar que sua aula começa em *20 minutos* ({horario_formatado}).\n"
                    f"Já está pronto(a)?"
                )
                
                try:
                    enviar_whatsapp(aluno.telefone, mensagem)
                    print(f"Lembrete enviado com sucesso para {aluno.nome}")
                except Exception as e:
                    print(f"Erro ao disparar lembrete para {aluno.nome}: {e}")

    except Exception as e:
        print(f"Erro no processamento do scheduler: {e}")
    finally:
        db.close()

# Configuração do agendador
scheduler = BackgroundScheduler()
# Rodar a cada 1 minuto para não perder nenhuma aula
scheduler.add_job(verificar_lembretes_20min, 'interval', minutes=1)
scheduler.start()