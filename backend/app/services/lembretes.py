import os
from datetime import timedelta

import holidays
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import BASE_URL, agora_br
from app.database import SessionLocal, get_db
from app.models import Aula, StatusAula, TipoAluno
from app.services.notificacoes_whatsapp import enviar_notificacao_rastreada


router = APIRouter(prefix="/jobs", tags=["automação"])
feriados_br = holidays.country_holidays("BR")


def lembretes_ativos() -> bool:
    return os.getenv("WHATSAPP_REMINDERS_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "sim",
    }


def verificar_lembretes(db: Session):
    if not lembretes_ativos():
        print("⏸️ Lembretes de WhatsApp pausados por configuração.")
        return 0
    agora = agora_br()

    if agora.date() in feriados_br:
        print(f"😴 Hoje é {feriados_br.get(agora.date())}. Lembretes pausados.")
        return 0

    inicio_janela = agora + timedelta(minutes=60)
    fim_janela = agora + timedelta(minutes=65)
    aulas = db.query(Aula).filter(
        Aula.status == StatusAula.marcada,
        Aula.lembrete_enviado.is_(False),
        Aula.data_inicio >= inicio_janela,
        Aula.data_inicio <= fim_janela,
    ).all()

    enviados = 0
    for aula in aulas:
        try:
            aluno = aula.aluno
            if not aluno:
                print(f"⚠️ Aula {aula.id} sem aluno; lembrete ignorado.")
                continue
            nome_aluno = aluno.nome or "Aluno"
            horario = aula.data_inicio.strftime("%H:%M")
            mensagem = (
                f"Hello {nome_aluno}! 👋\n\n"
                f"Passing by to let you know that your class starts in *1 hour* ({horario}).\n"
                "Are you ready? ⏰📚"
            )
            resultado = enviar_notificacao_rastreada(
                db,
                external_id=f"aula:{aula.id}:lembrete-1h",
                numero=aluno.telefone,
                tipo="lembrete_1h",
                parametros=[nome_aluno, horario],
                mensagem_fallback=mensagem,
                aluno_id=aluno.id,
                aula_id=aula.id,
            )
            if resultado:
                aula.lembrete_enviado = True
                db.commit()
                enviados += 1
                print(f"✅ Lembrete 1h aceito pelo provedor para {nome_aluno}")
            else:
                print(
                    f"❌ Lembrete 1h da aula {aula.id} não aceito: "
                    f"{resultado.erro_codigo} - {resultado.erro_mensagem}"
                )
        except Exception as exc:
            db.rollback()
            print(f"Erro ao processar lembrete da aula {aula.id}: {exc}")

    return enviados


@router.get("/verificar-lembretes")
def rota_verificar_lembretes(db: Session = Depends(get_db)):
    total = verificar_lembretes(db)
    return {"status": "sucesso", "lembretes_aceitos": total}


def verificar_lembretes_background():
    if not lembretes_ativos():
        print("⏸️ Lembretes de WhatsApp pausados por configuração.")
        return
    db = SessionLocal()
    try:
        verificar_lembretes(db)
        agora = agora_br()
        inicio_janela = agora + timedelta(hours=24)
        fim_janela = inicio_janela + timedelta(minutes=5)

        if inicio_janela.date() in feriados_br:
            print(
                f"🏖️ Aula em 24h cai em feriado "
                f"({feriados_br.get(inicio_janela.date())}). Pulando notificação."
            )
            return

        aulas_24h = db.query(Aula).filter(
            Aula.data_inicio >= inicio_janela,
            Aula.data_inicio <= fim_janela,
            Aula.status == StatusAula.marcada,
            Aula.lembrete_10h_enviado.is_(False),
        ).all()

        for aula in aulas_24h:
            aluno = aula.aluno
            if not aluno:
                print(f"⚠️ Aula {aula.id} sem aluno; lembrete 24h ignorado.")
                continue
            if aluno.tipo != TipoAluno.VIP:
                continue

            link_portal = f"{BASE_URL}/portal/{aluno.token_acesso}"
            data_aula = aula.data_inicio.strftime("%d/%m")
            horario = aula.data_inicio.strftime("%H:%M")
            mensagem = (
                f"Olá {aluno.nome}, passando para confirmar sua aula de amanhã! 🎓\n"
                f"Horário: *{horario}*\n\n"
                "Você pode ver os detalhes ou reagendar pelo seu portal:\n\n"
                f"{link_portal}\n\n"
                "Lembrando: você pode reagendar com até 3h de antecedência."
            )
            resultado = enviar_notificacao_rastreada(
                db,
                external_id=f"aula:{aula.id}:lembrete-24h",
                numero=aluno.telefone,
                tipo="lembrete_24h",
                parametros=[aluno.nome, data_aula, horario, link_portal],
                mensagem_fallback=mensagem,
                aluno_id=aluno.id,
                aula_id=aula.id,
            )
            if resultado:
                aula.lembrete_10h_enviado = True
                db.commit()
                print(f"✅ Lembrete 24h aceito pelo provedor para {aluno.nome}")
            else:
                print(
                    f"❌ Lembrete 24h da aula {aula.id} não aceito: "
                    f"{resultado.erro_codigo} - {resultado.erro_mensagem}"
                )
    finally:
        db.close()
