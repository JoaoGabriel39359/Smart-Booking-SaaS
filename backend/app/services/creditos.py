from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import agora_br
from app.models import Aluno, Aula, StatusAula


TIPO_CREDITO_MANUAL = "credito_manual"


def query_creditos_validos(db: Session, aluno_id: int, agora=None):
    agora = agora or agora_br()
    return db.query(Aula).filter(
        Aula.aluno_id == aluno_id,
        Aula.status == StatusAula.cancelado,
        Aula.validade_reposicao >= agora,
        Aula.credito_consumido_em.is_(None),
    )


def sincronizar_contador_creditos(db: Session, aluno: Aluno, agora=None) -> int:
    quantidade = query_creditos_validos(db, aluno.id, agora).count()
    aluno.creditos_reposicao = quantidade
    return quantidade


def consumir_credito(db: Session, aluno: Aluno, agora=None) -> Aula:
    agora = agora or agora_br()
    credito = (
        query_creditos_validos(db, aluno.id, agora)
        .order_by(Aula.validade_reposicao.asc(), Aula.id.asc())
        .with_for_update()
        .first()
    )
    if not credito:
        aluno.creditos_reposicao = 0
        raise HTTPException(status_code=400, detail="Você não possui créditos de reposição válidos.")

    credito.credito_consumido_em = agora
    db.flush()
    sincronizar_contador_creditos(db, aluno, agora)
    return credito


def ajustar_creditos_manualmente(db: Session, aluno: Aluno, quantidade: int, agora=None) -> int:
    if quantidade < 0:
        raise HTTPException(status_code=400, detail="A quantidade de créditos não pode ser negativa.")

    agora = agora or agora_br()
    creditos = (
        query_creditos_validos(db, aluno.id, agora)
        .order_by(Aula.validade_reposicao.asc(), Aula.id.asc())
        .with_for_update()
        .all()
    )
    atual = len(creditos)

    if quantidade < atual:
        for credito in creditos[: atual - quantidade]:
            credito.credito_consumido_em = agora
    elif quantidade > atual:
        for _ in range(quantidade - atual):
            db.add(Aula(
                aluno_id=aluno.id,
                data_inicio=agora,
                data_fim=agora,
                status=StatusAula.cancelado,
                tipo=TIPO_CREDITO_MANUAL,
                cancelada_em=agora,
                validade_reposicao=agora + timedelta(days=30),
            ))

    db.flush()
    return sincronizar_contador_creditos(db, aluno, agora)
