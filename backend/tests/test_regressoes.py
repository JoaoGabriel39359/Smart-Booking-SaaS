import pytest
from datetime import timedelta

from fastapi import BackgroundTasks, HTTPException

from app.core.config import agora_br
from app.routes.alunos import enviar_link_portal_whatsapp, obter_relatorio_aluno
from app.models import (
    Aluno,
    Aula,
    GradeProfessor,
    HistoricoAula,
    HorarioAula,
    Professor,
    StatusAula,
    TipoAluno,
    Turma,
)
from app.routes.aulas import cancelar_aula, horarios_livres, listar_historico_geral
from app.routes.relatorios import relatorio_creditos, relatorio_frequencia
from app.routes.turmas import deletar_turma
from app.services.creditos import consumir_credito
from app.services.disponibilidade import contar_reservas_simultaneas, resolver_grade_disponivel
from app.services.gerar_agenda import gerar_aulas_da_semana


def test_credito_consumido_nao_reaparece_no_relatorio(db_session):
    agora = agora_br()
    aluno = Aluno(
        nome="Credito",
        sobrenome="Real",
        telefone="551100000001",
        token_acesso="credito-real",
        tipo=TipoAluno.VIP,
    )
    db_session.add(aluno)
    db_session.flush()
    db_session.add(Aula(
        aluno_id=aluno.id,
        data_inicio=agora - timedelta(days=1),
        data_fim=agora - timedelta(days=1, hours=-1),
        status=StatusAula.cancelado,
        cancelada_em=agora - timedelta(days=1),
        validade_reposicao=agora + timedelta(days=20),
    ))
    db_session.commit()

    consumir_credito(db_session, aluno, agora)
    db_session.commit()

    db_session.refresh(aluno)
    assert aluno.creditos_reposicao == 0
    assert relatorio_creditos(db=db_session, usuario="teste") == []


def test_cancelamento_altera_somente_historico_da_aula(db_session):
    agora = agora_br()
    dia = (agora + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    aluno = Aluno(
        nome="Duas",
        sobrenome="Aulas",
        telefone="551100000002",
        token_acesso="duas-aulas",
        tipo=TipoAluno.VIP,
    )
    db_session.add(aluno)
    db_session.flush()
    primeira = Aula(
        aluno_id=aluno.id,
        data_inicio=dia,
        data_fim=dia + timedelta(hours=1),
        status=StatusAula.marcada,
    )
    segunda = Aula(
        aluno_id=aluno.id,
        data_inicio=dia + timedelta(hours=5),
        data_fim=dia + timedelta(hours=6),
        status=StatusAula.marcada,
    )
    db_session.add_all([primeira, segunda])
    db_session.flush()
    hist_primeira = HistoricoAula(
        aula_id=primeira.id,
        aluno_id=aluno.id,
        data_aula=primeira.data_inicio,
        chamada_realizada=False,
    )
    hist_segunda = HistoricoAula(
        aula_id=segunda.id,
        aluno_id=aluno.id,
        data_aula=segunda.data_inicio,
        chamada_realizada=False,
    )
    db_session.add_all([hist_primeira, hist_segunda])
    db_session.commit()

    cancelar_aula(
        primeira.id,
        aluno.token_acesso,
        BackgroundTasks(),
        db=db_session,
    )

    db_session.refresh(hist_primeira)
    db_session.refresh(hist_segunda)
    db_session.refresh(segunda)
    assert hist_primeira.chamada_realizada is True
    assert hist_segunda.chamada_realizada is False
    assert segunda.status == StatusAula.marcada


def test_frequencia_ignora_cancelamento_futuro(db_session):
    agora = agora_br()
    aluno = Aluno(
        nome="Frequencia",
        sobrenome="Correta",
        telefone="551100000003",
        token_acesso="frequencia",
        tipo=TipoAluno.VIP,
    )
    db_session.add(aluno)
    db_session.flush()
    realizada = Aula(
        aluno_id=aluno.id,
        data_inicio=agora - timedelta(days=1),
        data_fim=agora - timedelta(days=1, hours=-1),
        status=StatusAula.presente,
    )
    futura_cancelada = Aula(
        aluno_id=aluno.id,
        data_inicio=agora + timedelta(days=10),
        data_fim=agora + timedelta(days=10, hours=1),
        status=StatusAula.cancelado,
        validade_reposicao=agora + timedelta(days=30),
    )
    db_session.add_all([realizada, futura_cancelada])
    db_session.flush()
    db_session.add_all([
        HistoricoAula(
            aula_id=realizada.id,
            aluno_id=aluno.id,
            data_aula=realizada.data_inicio,
            status_presenca=True,
            chamada_realizada=True,
        ),
        HistoricoAula(
            aula_id=futura_cancelada.id,
            aluno_id=aluno.id,
            data_aula=futura_cancelada.data_inicio,
            status_presenca=False,
            chamada_realizada=True,
            observacao="Aula Cancelada",
        ),
    ])
    db_session.commit()

    resultado = relatorio_frequencia(dias=30, db=db_session, usuario="teste")

    assert len(resultado) == 1
    assert resultado[0]["total_aulas"] == 1
    assert resultado[0]["presencas"] == 1
    assert resultado[0]["faltas"] == 0
    assert resultado[0]["cancelamentos"] == 0


def test_capacidade_conta_turma_como_uma_reserva(db_session):
    inicio = agora_br() + timedelta(days=1)
    fim = inicio + timedelta(hours=1)
    professor = Professor(nome="Professor", ativo=True)
    turma = Turma(nome_turma="Equipe", tipo="TEAM")
    db_session.add_all([professor, turma])
    db_session.flush()
    alunos = [
        Aluno(
            nome=f"Aluno {indice}",
            sobrenome="Equipe",
            telefone=f"55110000001{indice}",
            tipo=TipoAluno.TEAM,
            turma_id=turma.id,
        )
        for indice in range(2)
    ]
    db_session.add_all(alunos)
    db_session.flush()
    for aluno in alunos:
        db_session.add(Aula(
            aluno_id=aluno.id,
            turma_id=turma.id,
            professor_id=professor.id,
            data_inicio=inicio,
            data_fim=fim,
            status=StatusAula.marcada,
            google_event_id="evento-da-turma",
        ))
    db_session.commit()

    assert contar_reservas_simultaneas(
        db_session, inicio, fim, professor.id
    ) == 1


def test_mesmo_horario_e_independente_por_professor(db_session):
    inicio = (agora_br() + timedelta(days=1)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    fim = inicio + timedelta(hours=1)
    vinicios = Professor(nome="Vinicios", ativo=True)
    eddy = Professor(nome="Eddy", ativo=True)
    aluno = Aluno(
        nome="Aluno",
        sobrenome="Teste",
        telefone="551100000020",
        tipo=TipoAluno.VIP,
    )
    db_session.add_all([vinicios, eddy, aluno])
    db_session.flush()

    grade_vinicios = GradeProfessor(
        dia_semana=inicio.weekday(),
        hora_inicio="15:00",
        hora_fim="16:00",
        professor_id=vinicios.id,
        capacidade=1,
    )
    grade_eddy = GradeProfessor(
        dia_semana=inicio.weekday(),
        hora_inicio="15:00",
        hora_fim="16:00",
        professor_id=eddy.id,
        capacidade=1,
    )
    db_session.add_all([grade_vinicios, grade_eddy])
    db_session.flush()
    db_session.add(Aula(
        aluno_id=aluno.id,
        professor_id=vinicios.id,
        data_inicio=inicio,
        data_fim=fim,
        status=StatusAula.marcada,
    ))
    db_session.commit()

    assert contar_reservas_simultaneas(db_session, inicio, fim, vinicios.id) == 1
    assert contar_reservas_simultaneas(db_session, inicio, fim, eddy.id) == 0

    turno_disponivel = resolver_grade_disponivel(
        db_session,
        inicio,
        fim,
        grade_id_preferida=grade_eddy.id,
    )
    assert turno_disponivel is not None
    assert turno_disponivel.id == grade_eddy.id


def test_horarios_respeitam_duracao_de_duas_horas(db_session):
    data = (agora_br() + timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    turma = Turma(
        nome_turma="Duas Horas",
        tipo="TEAM",
        duracao_minutos=120,
    )
    db_session.add(turma)
    db_session.flush()
    aluno = Aluno(
        nome="Longa",
        sobrenome="Duracao",
        telefone="551100000004",
        token_acesso="duas-horas",
        tipo=TipoAluno.TEAM,
        turma_id=turma.id,
    )
    grade = GradeProfessor(
        dia_semana=data.weekday(),
        hora_inicio="08:00",
        hora_fim="12:00",
        ativo=True,
        capacidade=1,
    )
    db_session.add_all([aluno, grade])
    db_session.commit()

    resultado = horarios_livres(
        data=data.strftime("%d-%m-%Y"),
        token=aluno.token_acesso,
        db=db_session,
    )
    horas = {slot["hora"] for slot in resultado["horarios_livres"]}

    assert horas == {"08:00", "09:00", "10:00"}
    assert "11:00" not in horas


def test_excluir_turma_preserva_historico_e_credito(db_session):
    agora = agora_br()
    turma = Turma(nome_turma="Preservar", tipo="TEAM")
    aluno = Aluno(
        nome="Historico",
        sobrenome="Seguro",
        telefone="551100000005",
        tipo=TipoAluno.TEAM,
        turma=turma,
    )
    db_session.add_all([turma, aluno])
    db_session.flush()
    realizada = Aula(
        aluno_id=aluno.id,
        turma_id=turma.id,
        data_inicio=agora - timedelta(days=2),
        data_fim=agora - timedelta(days=2, hours=-1),
        status=StatusAula.presente,
    )
    futura = Aula(
        aluno_id=aluno.id,
        turma_id=turma.id,
        data_inicio=agora + timedelta(days=2),
        data_fim=agora + timedelta(days=2, hours=1),
        status=StatusAula.marcada,
    )
    credito = Aula(
        aluno_id=aluno.id,
        turma_id=turma.id,
        data_inicio=agora + timedelta(days=3),
        data_fim=agora + timedelta(days=3, hours=1),
        status=StatusAula.cancelado,
        cancelada_em=agora,
        validade_reposicao=agora + timedelta(days=30),
    )
    db_session.add_all([realizada, futura, credito])
    db_session.flush()
    historico = HistoricoAula(
        aula_id=realizada.id,
        aluno_id=aluno.id,
        data_aula=realizada.data_inicio,
        status_presenca=True,
        chamada_realizada=True,
    )
    db_session.add(historico)
    db_session.commit()
    ids = realizada.id, futura.id, credito.id

    deletar_turma(turma.id, db=db_session, usuario="teste")

    realizada_salva = db_session.get(Aula, ids[0])
    assert realizada_salva is not None
    assert realizada_salva.turma_id is None
    assert db_session.get(HistoricoAula, historico.id) is not None
    assert db_session.get(Aula, ids[1]) is None
    credito_salvo = db_session.get(Aula, ids[2])
    assert credito_salvo is not None
    assert credito_salvo.turma_id is None
    assert credito_salvo.validade_reposicao is not None


def test_agenda_gerada_herda_professor_da_turma(db_session, monkeypatch):
    agora = agora_br()
    alvo = agora + timedelta(days=1)
    professor = Professor(nome="Responsavel", ativo=True)
    turma = Turma(
        nome_turma="Com Professor",
        tipo="TEAM",
        duracao_minutos=60,
        professor=professor,
    )
    aluno = Aluno(
        nome="Gerado",
        sobrenome="Professor",
        telefone="551100000006",
        tipo=TipoAluno.TEAM,
        turma=turma,
    )
    horario = HorarioAula(
        turma=turma,
        dia_da_semana=alvo.weekday(),
        horario=alvo.replace(hour=20, minute=0, second=0, microsecond=0).time(),
    )
    db_session.add_all([professor, turma, aluno, horario])
    db_session.commit()
    monkeypatch.setattr(
        "app.services.gerar_agenda.criar_evento",
        lambda *args, **kwargs: ("evento-gerado", None),
    )

    gerar_aulas_da_semana(db_session)

    aulas = db_session.query(Aula).filter(Aula.aluno_id == aluno.id).all()
    assert aulas
    assert all(aula.professor_id == professor.id for aula in aulas)


def test_historico_separa_pendentes_de_concluidas(db_session):
    agora = agora_br()
    professor = Professor(nome="Docente", ativo=True)
    turma = Turma(nome_turma="Turma Histórica", tipo="TEAM", professor=professor)
    aluno = Aluno(nome="Aluno", sobrenome="Histórico", telefone="551100000007", tipo=TipoAluno.TEAM, turma=turma)
    db_session.add_all([professor, turma, aluno])
    db_session.flush()
    aula_pendente = Aula(
        aluno=aluno, turma=turma, professor=professor,
        data_inicio=agora - timedelta(days=2),
        data_fim=agora - timedelta(days=2, hours=-1),
        status=StatusAula.marcada,
    )
    aula_concluida = Aula(
        aluno=aluno, turma=turma, professor=professor,
        data_inicio=agora - timedelta(days=1),
        data_fim=agora - timedelta(days=1, hours=-1),
        status=StatusAula.presente,
    )
    db_session.add_all([aula_pendente, aula_concluida])
    db_session.flush()
    db_session.add_all([
        HistoricoAula(aula=aula_pendente, aluno=aluno, data_aula=aula_pendente.data_inicio, chamada_realizada=False),
        HistoricoAula(
            aula=aula_concluida, aluno=aluno, data_aula=aula_concluida.data_inicio,
            status_presenca=True, chamada_realizada=True,
        ),
    ])
    db_session.commit()

    pendentes = listar_historico_geral(False, db=db_session, usuario="teste")
    concluidas = listar_historico_geral(True, db=db_session, usuario="teste")

    assert len(pendentes) == 1
    assert len(concluidas) == 1
    assert pendentes[0]["data"] == aula_pendente.data_inicio.isoformat()
    assert concluidas[0]["data"] == aula_concluida.data_inicio.isoformat()
    assert concluidas[0]["nome_exibicao"] == turma.nome_turma
    assert concluidas[0]["professor_nome"] == professor.nome


def test_relatorio_aluno_preserva_duas_aulas_no_mesmo_dia(db_session):
    agora = agora_br()
    aluno = Aluno(
        nome="Duas", sobrenome="No Mesmo Dia", telefone="551100000008", tipo=TipoAluno.VIP,
    )
    db_session.add(aluno)
    db_session.flush()
    horarios = [
        (agora - timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0),
        (agora - timedelta(days=3)).replace(hour=18, minute=0, second=0, microsecond=0),
    ]
    for indice, inicio in enumerate(horarios):
        aula = Aula(
            aluno=aluno, data_inicio=inicio, data_fim=inicio + timedelta(hours=1),
            status=StatusAula.presente if indice == 0 else StatusAula.ausente,
        )
        db_session.add(aula)
        db_session.flush()
        db_session.add(HistoricoAula(
            aula=aula, aluno=aluno, data_aula=inicio,
            status_presenca=indice == 0, chamada_realizada=True, desempenho="Bom",
        ))
    db_session.commit()

    relatorio = obter_relatorio_aluno(aluno.id, db=db_session, usuario="teste")

    assert relatorio["resumo"] == {
        "total_aulas": 2, "presencas": 1, "faltas": 1, "taxa_presenca": 50.0,
    }
    assert len(relatorio["registros"]) == 2
    assert {item["data_inicio"] for item in relatorio["registros"]} == {
        horario.isoformat() for horario in horarios
    }


def test_envio_portal_nao_confirma_quando_evolution_falha(db_session, monkeypatch):
    aluno = Aluno(
        nome="Falha", sobrenome="WhatsApp", telefone="551100000009",
        token_acesso="falha-whatsapp", tipo=TipoAluno.VIP,
    )
    db_session.add(aluno)
    db_session.commit()
    monkeypatch.setattr("app.routes.alunos.BASE_URL", "https://agenda.exemplo.com")
    monkeypatch.setattr("app.routes.alunos.enviar_whatsapp", lambda *_: False)

    with pytest.raises(HTTPException) as exc_info:
        enviar_link_portal_whatsapp(aluno.id, db=db_session, usuario="teste")

    assert exc_info.value.status_code == 502
    assert "instância" in exc_info.value.detail


def test_envio_portal_bloqueia_link_local(db_session, monkeypatch):
    aluno = Aluno(
        nome="Link", sobrenome="Local", telefone="551100000010",
        token_acesso="link-local", tipo=TipoAluno.VIP,
    )
    db_session.add(aluno)
    db_session.commit()
    monkeypatch.setattr("app.routes.alunos.BASE_URL", "http://127.0.0.1:8000")

    with pytest.raises(HTTPException) as exc_info:
        enviar_link_portal_whatsapp(aluno.id, db=db_session, usuario="teste")

    assert exc_info.value.status_code == 400
    assert "URL pública" in exc_info.value.detail
