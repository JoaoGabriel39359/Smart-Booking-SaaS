import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import Date, cast

sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models import Aula, Aluno
from app.services.whatsapp import enviar_whatsapp

def limpar_creditos_vencidos(db):
    """Transforma créditos de reposição vencidos em status 'ausente'"""
    agora = datetime.now()
    
    # Busca aulas canceladas (que são créditos) cuja validade já passou
    vencidos = db.query(Aula).filter(
        Aula.status == "cancelado",
        Aula.validade_reposicao < agora
    ).all()
    
    if vencidos:
        print(f"🧹 Limpeza: {len(vencidos)} créditos expirados encontrados.")
        for aula in vencidos:
            aula.status = "ausente" # O crédito deixa de existir para o portal
        db.commit()
    else:
        print("🧹 Limpeza: Nenhum crédito expirado para remover.")

def rodar_cron_completo():
    db = SessionLocal()
    agora = datetime.now()
    hoje = agora.date() # <-- ADICIONEI ESSA LINHA (estava faltando o 'hoje')
    
    # URL BASE
    base_url = "https://smart-booking-saas.onrender.com"

    print(f"--- Iniciando Cron Job: {agora.strftime('%d/%m/%Y %H:%M:%S')} ---")

    # --- PARTE 1: VENCIMENTO DE CRÉDITOS --- (Igual ao seu)
    prazos = [15, 1]
    for dias in prazos:
        data_alvo = hoje + timedelta(days=dias)
        creditos = db.query(Aula).filter(
            Aula.status == "cancelado",
            Aula.validade_reposicao >= datetime.combine(data_alvo, datetime.min.time()),
            Aula.validade_reposicao <= datetime.combine(data_alvo, datetime.max.time())
        ).all()
        for aula in creditos:
            aluno = aula.aluno
            link_portal = f"{base_url}/portal/{aluno.token_acesso}"
            tempo_texto = "vence em *15 dias*" if dias == 15 else "vence *AMANHÃ*"
            msg = (f"Olá {aluno.nome}! ⏳\n\nSua reposição {tempo_texto}.\nAgende pelo portal:\n{link_portal}")
            try:
                enviar_whatsapp(aluno.telefone, msg)
                print(f"✅ Alerta de vencimento: {aluno.nome}")
            except: pass

    # --- PARTE 2: CONFIRMAÇÃO 24H ANTES --- (Igual ao seu)
    amanha = hoje + timedelta(days=1)
    vips_amanha = db.query(Aula).join(Aluno).filter(
        cast(Aula.data_inicio, Date) == amanha,
        Aluno.tipo == 'VIP'
    ).all()
    for aula in vips_amanha:
        link_portal = f"{base_url}/portal/{aula.aluno.token_acesso}"
        msg = (f"Olá {aula.aluno.nome}! Aula confirmada para AMANHÃ às {aula.data_inicio.strftime('%H:%M')}?\n{link_portal}")
        try:
            enviar_whatsapp(aula.aluno.telefone, msg)
            print(f"✅ Alerta 24h: {aula.aluno.nome}")
        except: pass

    # --- PARTE 3: LEMBRETE 20 MINUTOS ANTES ---
    # AJUSTE AQUI: Usei a "janela zona" de 5 horas para garantir que o fuso horário não te bloqueie no teste
    janela_inicio = agora - timedelta(hours=5)
    janela_fim = agora + timedelta(hours=5)
    
    print(f"DEBUG: Buscando aulas na janela de teste: {janela_inicio.strftime('%H:%M')} até {janela_fim.strftime('%H:%M')}")

    aulas_do_dia = db.query(Aula).filter(
        cast(Aula.data_inicio, Date) == hoje,
        Aula.lembrete_enviado == False,    
        Aula.status == 'marcada'           
    ).all()

    for a in aulas_do_dia:
        status_str = a.status.value if hasattr(a.status, 'value') else str(a.status)
        
        # Verifica se a aula está na janela, se está 'marcada' e se ainda não enviamos o lembrete
        if (janela_inicio <= a.data_inicio <= janela_fim) and (status_str == 'marcada') and (not a.lembrete_enviado):
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

    db.commit()
    db.close()
    print("--- Processamento concluído ---")

if __name__ == "__main__":
    rodar_cron_completo()

def limpar_creditos_vencidos(db):
    agora = datetime.now()
    
    # Busca aulas que geraram crédito (canceladas) e que já passaram da validade
    vencidos = db.query(Aula).filter(
        Aula.status == "cancelado",
        Aula.validade_reposicao < agora
    ).all()
    
    for aula in vencidos:
        aula.status = "ausente" # Ou um status novo como "expirado"
        print(f"⚪ Crédito do aluno {aula.aluno.nome} expirou e foi removido.")
    
    db.commit()