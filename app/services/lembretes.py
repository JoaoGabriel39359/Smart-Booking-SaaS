from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import holidays
from app.database import get_db, SessionLocal 
from app.models import Aula, StatusAula, TipoAluno
from app.services.whatsapp import enviar_whatsapp

router = APIRouter(prefix="/jobs", tags=["automação"])
feriados_br = holidays.country_holidays('BR')

def verificar_lembretes(db: Session):
    agora = datetime.now()

    if agora in feriados_br:
        print(f"😴 Hoje é {feriados_br.get(agora)}. Lembretes pausados.")
        return 0
    
    inicio_janela = agora + timedelta(minutes=60)
    fim_janela = agora + timedelta(minutes=65)

    aulas = db.query(Aula).filter(
        Aula.status == StatusAula.marcada,
        Aula.lembrete_enviado == False,
        Aula.data_inicio >= inicio_janela,
        Aula.data_inicio <= fim_janela
    ).all()

    enviados = 0
    for aula in aulas:
        try:
            nome_aluno = aula.aluno.nome if aula.aluno else "Aluno"
            horario = aula.data_inicio.strftime('%H:%M')
            
            msg = (
                    f"Hello {nome_aluno}! 👋\n\n"
                    f"Passing by to let you know that your class starts in *1 hour* ({horario}).\n"
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

@router.get("/verificar-lembretes")
def rota_verificar_lembretes(db: Session = Depends(get_db)):
    total = verificar_lembretes(db)
    return {"status": "sucesso", "lembretes_enviados": total}

def verificar_lembretes_background():
    db = SessionLocal()
    try:
        verificar_lembretes(db)
        agora = datetime.now()
        check_24h = agora + timedelta(hours=24)

        if check_24h in feriados_br:
            print(f"🏖️ Aula em 24h cai em feriado ({feriados_br.get(check_24h)}). Pulando notificação.")
        else:
            aulas_24h = db.query(Aula).filter(
                Aula.data_inicio >= check_24h,
                Aula.data_inicio <= check_24h + timedelta(minutes=5),
                Aula.status == StatusAula.marcada,
                Aula.lembrete_24h_enviado == False
            ).all()

            for aula in aulas_24h:
                aluno = aula.aluno
                if aluno.tipo == TipoAluno.VIP:
                    token_do_aluno = aluno.token_acesso
                    link_portal = f"https://smart-booking-saas.onrender.com/portal/{token_do_aluno}"

                    msg = (
                        f"Olá {aluno.nome}, passando para confirmar sua aula de amanhã! 🎓\n"
                        f"Horário: *{aula.data_inicio.strftime('%H:%M')}*\n\n"
                        f"Você pode ver os detalhes ou reagendar pelo seu portal no link abaixo:\n\n" 
                        f"{link_portal}\n\n"
                        f"Lembrando: você pode reagendar com até 3h de antecedência."
                    )
                    sucesso = enviar_whatsapp(aluno.telefone, msg)
                    
                    if sucesso:
                        aula.lembrete_24h_enviado = True
                        print(f"✅ Lembrete 24h enviado para VIP: {aluno.nome}")
        
        db.commit()
    finally:
        db.close()