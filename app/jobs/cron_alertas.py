import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import Date, cast

from app.database import SessionLocal
from app.models import Aula, Aluno, StatusAula
from app.services.whatsapp import enviar_whatsapp


def limpar_creditos_vencidos(db):
    """Transforma créditos de reposição vencidos em status 'ausente'"""
    agora = datetime.now()
    
    # Busca aulas canceladas (que são créditos) cuja validade já passou
    vencidos = db.query(Aula).filter(
        Aula.status.in_(["cancelado", StatusAula.cancelado]),
        Aula.validade_reposicao < agora
    ).all()
    
    if vencidos:
        print(f"🧹 Limpeza: {len(vencidos)} créditos expirados encontrados.")
        for aula in vencidos:
            aula.status = StatusAula.ausente
        db.commit()
    else:
        print("🧹 Limpeza: Nenhum crédito expirado para remover.")


def rodar_cron_completo():
    db = SessionLocal()
    try:
        agora = datetime.now()
        hoje = agora.date()
        base_url = os.getenv("BASE_URL", "https://smart-booking-saas.onrender.com")

        print(f"--- Iniciando Cron Job: {agora.strftime('%d/%m/%Y %H:%M:%S')} ---")

        # --- PARTE 1: VENCIMENTO DE CRÉDITOS ---
        prazos = [15, 1]
        for dias in prazos:
            data_alvo = hoje + timedelta(days=dias)
            creditos = db.query(Aula).filter(
                Aula.status.in_(["cancelado", StatusAula.cancelado]),
                Aula.validade_reposicao >= datetime.combine(data_alvo, datetime.min.time()),
                Aula.validade_reposicao <= datetime.combine(data_alvo, datetime.max.time())
            ).all()
            for aula in creditos:
                aluno = aula.aluno
                if not aluno:
                    continue
                link_portal = f"{base_url}/portal/{aluno.token_acesso}"
                tempo_texto = "vence em *15 dias*" if dias == 15 else "vence *AMANHÃ*"
                msg = (f"Olá {aluno.nome}! ⏳\n\nSua reposição {tempo_texto}.\nAgende pelo portal:\n{link_portal}")
                try:
                    enviar_whatsapp(aluno.telefone, msg)
                    print(f"✅ Alerta de vencimento: {aluno.nome}")
                except Exception as e:
                    print(f"❌ Erro envio alerta vencimento: {e}")

        # --- PARTE 2: CONFIRMAÇÃO 24H ANTES ---
        amanha = hoje + timedelta(days=1)
        vips_amanha = db.query(Aula).join(Aluno).filter(
            cast(Aula.data_inicio, Date) == amanha,
            Aluno.tipo == 'VIP'
        ).all()
        for aula in vips_amanha:
            if not aula.aluno:
                continue
            link_portal = f"{base_url}/portal/{aula.aluno.token_acesso}"
            msg = (f"Olá {aula.aluno.nome}! Aula confirmada para AMANHÃ às {aula.data_inicio.strftime('%H:%M')}?\n{link_portal}")
            try:
                enviar_whatsapp(aula.aluno.telefone, msg)
                print(f"✅ Alerta 24h: {aula.aluno.nome}")
            except Exception as e:
                print(f"❌ Erro envio 24h: {e}")

        # --- PARTE 3: LEMBRETE 20 MINUTOS ANTES ---
        janela_inicio = agora - timedelta(hours=5)
        janela_fim = agora + timedelta(hours=5)
        
        aulas_do_dia = db.query(Aula).filter(
            cast(Aula.data_inicio, Date) == hoje,
            Aula.lembrete_enviado == False,    
            Aula.status.in_(["marcada", StatusAula.marcada])
        ).all()

        for a in aulas_do_dia:
            if not a.aluno:
                continue
            status_str = a.status.value if hasattr(a.status, 'value') else str(a.status)
            
            if (janela_inicio <= a.data_inicio <= janela_fim) and (status_str.lower() == 'marcada') and (not a.lembrete_enviado):
                horario = a.data_inicio.strftime('%H:%M')
                link_portal = f"{base_url}/portal/{a.aluno.token_acesso}"

                msg = (
                    f"Olá, *{a.aluno.nome}*! 🧘‍♂️\n\n"
                    f"Sua aula começa em breve (às *{horario}*). 🕒\n\n"
                    f"Acesse seu portal: {link_portal}\n\n caso precise reagendar ou cancelar. \n\n"
                    f"Até logo! 🚀"
                )
                try:
                    enviar_whatsapp(a.aluno.telefone, msg)
                    a.lembrete_enviado = True 
                    print(f"✅ Lembrete enviado para: {a.aluno.nome}")
                except Exception as e:
                    print(f"❌ Erro ao enviar: {e}")

        limpar_creditos_vencidos(db)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"❌ Erro na execução do cron de alertas: {e}")
    finally:
        db.close()
        print("--- Processamento concluído ---")

if __name__ == "__main__":
    rodar_cron_completo()
