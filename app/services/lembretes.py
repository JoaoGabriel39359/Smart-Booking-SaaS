from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import Aula
from app.services.whatsapp import enviar_whatsapp

def verificar_lembretes():
    db = SessionLocal()
    try:
        agora = datetime.now()
        # Define a janela: de AGORA até DAQUI A 20 MINUTOS
        limite = agora + timedelta(minutes=20)

        aulas = db.query(Aula).filter(
            Aula.status == "marcada",
            Aula.lembrete_enviado == False,
            Aula.data_inicio >= agora,
            Aula.data_inicio <= limite
        ).all()

        for aula in aulas:
            try:
                nome = aula.aluno.nome
                # Envia o zap individual (funciona para VIP, DUO ou TEAM)
                enviar_whatsapp(
                    numero=aula.aluno.telefone,
                    mensagem=f"Olá {nome}! 👋 Lembrete: sua aula começa em 20 min ({aula.data_inicio.strftime('%H:%M')})."
                )
                
                # Marca como enviado e salva IMEDIATAMENTE no banco
                aula.lembrete_enviado = True
                db.commit() 
                print(f"✅ Lembrete enviado para: {nome}")
                
            except Exception as e:
                db.rollback() # Se der erro em um aluno, cancela a alteração DELE
                print(f"❌ Erro ao enviar para {aula.aluno.nome}: {e}")
                continue 
    except Exception as e:
        print(f"💥 Erro geral no serviço de lembretes: {e}")
    finally:
        db.close() # Apenas fecha a conexão, sem commit aqui.