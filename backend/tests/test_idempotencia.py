from datetime import time, timedelta

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.config import agora_br
from app.models import (
    Aluno,
    Aula,
    HorarioAula,
    StatusAula,
    TipoAluno,
    Turma,
)
from app.routes.aulas import criar_aula_avulsa
from app.routes.turmas import criar_turma, editar_turma
from app.services.gerar_agenda import gerar_aulas_da_semana


def _aluno(nome: str, email: str) -> Aluno:
    return Aluno(
        nome=nome,
        sobrenome="Teste",
        email=email,
        telefone="11999999999",
        tipo=TipoAluno.VIP,
    )


def test_banco_impede_aula_ativa_duplicada(db_session):
    aluno = _aluno("Aluno único", "unico@example.com")
    db_session.add(aluno)
    db_session.commit()

    inicio = (agora_br() + timedelta(days=2)).replace(
        hour=13, minute=0, second=0, microsecond=0
    )
    primeira = Aula(
        aluno_id=aluno.id,
        data_inicio=inicio,
        data_fim=inicio + timedelta(hours=1),
        status=StatusAula.marcada,
    )
    db_session.add(primeira)
    db_session.commit()

    db_session.add(
        Aula(
            aluno_id=aluno.id,
            data_inicio=inicio,
            data_fim=inicio + timedelta(hours=1),
            status=StatusAula.marcada,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert (
        db_session.query(Aula)
        .filter(
            Aula.aluno_id == aluno.id,
            Aula.data_inicio == inicio,
            Aula.status == StatusAula.marcada,
        )
        .count()
        == 1
    )


def test_geracao_semanal_e_direcionada_e_idempotente(db_session):
    amanha = agora_br() + timedelta(days=1)
    aluno_alvo = _aluno("Aluno alvo", "alvo@example.com")
    aluno_outro = _aluno("Aluno outro", "outro@example.com")
    turma_alvo = Turma(
        nome_turma="Turma alvo",
        tipo="VIP",
        duracao_minutos=60,
        alunos=[aluno_alvo],
    )
    turma_outra = Turma(
        nome_turma="Turma outra",
        tipo="VIP",
        duracao_minutos=60,
        alunos=[aluno_outro],
    )
    db_session.add_all([turma_alvo, turma_outra])
    db_session.flush()
    db_session.add_all(
        [
            HorarioAula(
                turma_id=turma_alvo.id,
                dia_da_semana=amanha.weekday(),
                horario=time(13, 0),
            ),
            HorarioAula(
                turma_id=turma_outra.id,
                dia_da_semana=amanha.weekday(),
                horario=time(15, 0),
            ),
        ]
    )
    db_session.commit()

    primeira_execucao = gerar_aulas_da_semana(db_session, turma_alvo.id)
    segunda_execucao = gerar_aulas_da_semana(db_session, turma_alvo.id)

    aulas_alvo = (
        db_session.query(Aula)
        .filter(Aula.aluno_id == aluno_alvo.id)
        .order_by(Aula.data_inicio)
        .all()
    )
    assert primeira_execucao == 4
    assert segunda_execucao == 0
    assert len(aulas_alvo) == 4
    assert len({aula.data_inicio for aula in aulas_alvo}) == 4
    assert all(
        aulas_alvo[indice + 1].data_inicio - aulas_alvo[indice].data_inicio
        == timedelta(days=7)
        for indice in range(3)
    )
    assert db_session.query(Aula).filter(Aula.aluno_id == aluno_outro.id).count() == 0


def test_criar_turma_responde_antes_da_sincronizacao(
    db_session, mock_google_calendar
):
    aluno = _aluno("Aluno da turma", "turma@example.com")
    db_session.add(aluno)
    db_session.commit()
    amanha = agora_br() + timedelta(days=1)
    tarefas = BackgroundTasks()

    resposta = criar_turma(
        {
            "nome_turma": "Turma rápida",
            "tipo": "VIP",
            "duracao_minutos": 60,
            "professor_id": None,
            "meet_link": None,
            "aluno_ids": [aluno.id],
            "horarios": [
                {
                    "dia": amanha.weekday(),
                    "hora": "13:00",
                }
            ],
        },
        tarefas,
        db=db_session,
        usuario="teste",
    )

    assert resposta["agenda_sincronizando"] is True
    assert db_session.query(Turma).filter(Turma.nome_turma == "Turma rápida").count() == 1
    assert db_session.query(Aula).count() == 0
    assert len(tarefas.tasks) == 1
    mock_google_calendar["criar"].assert_not_called()


def test_repetir_aula_avulsa_retorna_conflito_sem_duplicar(
    db_session, mock_google_calendar
):
    aluno = _aluno("Aluno avulso", "avulso@example.com")
    db_session.add(aluno)
    db_session.commit()
    inicio = (agora_br() + timedelta(days=2)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    dados = {
        "aluno_id": aluno.id,
        "data_inicio": inicio.isoformat(),
        "duracao_minutos": 60,
        "meet_link": None,
    }
    primeiras_tarefas = BackgroundTasks()

    resposta = criar_aula_avulsa(
        dados,
        primeiras_tarefas,
        db=db_session,
        usuario="teste",
    )

    assert resposta["google_sync_pending"] is True
    assert db_session.query(Aula).count() == 1
    assert len(primeiras_tarefas.tasks) == 1
    mock_google_calendar["criar"].assert_not_called()

    with pytest.raises(HTTPException) as erro:
        criar_aula_avulsa(
            dados,
            BackgroundTasks(),
            db=db_session,
            usuario="teste",
        )

    assert erro.value.status_code == 409
    assert db_session.query(Aula).count() == 1

def test_editar_turma_salva_antes_da_sincronizacao(
    db_session, mock_google_calendar
):
    amanha = agora_br() + timedelta(days=1)
    inicio = amanha.replace(hour=13, minute=0, second=0, microsecond=0)
    aluno = _aluno("Aluno editado", "editado@example.com")
    turma = Turma(
        nome_turma="Turma editada",
        tipo="VIP",
        duracao_minutos=60,
        alunos=[aluno],
    )
    horario = HorarioAula(
        turma=turma,
        dia_da_semana=amanha.weekday(),
        horario=time(13, 0),
    )
    db_session.add_all([turma, aluno, horario])
    db_session.flush()
    db_session.add(
        Aula(
            aluno_id=aluno.id,
            turma_id=turma.id,
            data_inicio=inicio,
            data_fim=inicio + timedelta(hours=1),
            status=StatusAula.marcada,
            google_event_id="evento-antigo",
        )
    )
    db_session.commit()
    tarefas = BackgroundTasks()

    resposta = editar_turma(
        turma.id,
        {
            "nome_turma": "Turma editada",
            "tipo": "VIP",
            "duracao_minutos": 60,
            "professor_id": None,
            "meet_link": None,
            "aluno_ids": [aluno.id],
            "horarios": [{"dia": amanha.weekday(), "hora": "13:00"}],
        },
        tarefas,
        db=db_session,
        usuario="teste",
    )

    assert resposta["agenda_sincronizando"] is True
    assert resposta["aulas_removidas"] == 1
    assert db_session.query(Aula).count() == 0
    assert len(tarefas.tasks) == 1
    mock_google_calendar["criar"].assert_not_called()
    mock_google_calendar["remover"].assert_not_called()
