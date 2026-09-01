from sqlalchemy.orm import Session

from app.models import Aluno, Turma

DURACAO_PADRAO_MINUTOS = 60


def duracao_aula_minutos(db: Session, aluno: Aluno) -> int:
    """
    Duracao real da aula do aluno em minutos.
    Antes o sistema cravava 1 hora em todo lugar, o que fazia o plano de 2h nunca
    valer na pratica. Agora respeitamos a duracao configurada na turma do aluno.
    """
    if aluno is not None and aluno.turma_id:
        turma = db.query(Turma).filter(Turma.id == aluno.turma_id).first()
        if turma and turma.duracao_minutos:
            return int(turma.duracao_minutos)
    return DURACAO_PADRAO_MINUTOS
