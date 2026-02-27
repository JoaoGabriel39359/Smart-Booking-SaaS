import os
import sys
from datetime import datetime, timedelta

# Garante que o script enxergue a pasta 'app'
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models import Aula, Aluno
from app.services.whatsapp import enviar_whatsapp

def verificar_e_notificar():
    db = SessionLocal()
    hoje = datetime.now().date()
    
    # Vamos verificar quem vence em 15 dias e quem vence amanhã (1 dia)
    prazos = [15, 1]
    
    for dias in prazos:
        data_alvo = hoje + timedelta(days=dias)
        
        # Busca aulas canceladas que vencem EXATAMENTE na data_alvo
        # Comparamos apenas a data (ignorando a hora)
        creditos = db.query(Aula).filter(
            Aula.status == "cancelado",
            Aula.validade_reposicao >= datetime.combine(data_alvo, datetime.min.time()),
            Aula.validade_reposicao <= datetime.combine(data_alvo, datetime.max.time())
        ).all()

        for aula in creditos:
            aluno = aula.aluno

            link_portal = f"https://pseudoheroic-semispontaneous-gerda.ngrok-free.dev/portal/{aluno.id}"
            
            if dias == 15:
                tempo_texto = "vence em *15 dias*"
            else:
                tempo_texto = "vence *AMANHÃ*"

            msg = (
                f"Olá {aluno.nome}! ⏳\n\n"
                f"Passando para lembrar que seu crédito de reposição {tempo_texto} "
                f"({aula.validade_reposicao.strftime('%d/%m')}).\n\n"
                f"Acesse a agenda para não perder o prazo e garantir sua aula!"
                f" Não perca o prazo! Agende sua reposição agora pelo portal:\n{link_portal}"
            )
            
            try:
                enviar_whatsapp(aluno.telefone, msg)
                print(f"✅ Alerta de {dias} dias enviado para {aluno.nome}")
            except Exception as e:
                print(f"❌ Erro ao enviar para {aluno.nome}: {e}")
    
    db.close()

if __name__ == "__main__":
    print(f"--- Iniciando verificação de vencimentos: {datetime.now()} ---")
    verificar_e_notificar()
    print("--- Verificação concluída ---")