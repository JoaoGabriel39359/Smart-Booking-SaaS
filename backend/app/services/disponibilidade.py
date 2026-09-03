from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Aula, GradeProfessor, Professor, StatusAula


STATUS_OCUPADOS = (StatusAula.marcada, StatusAula.presente)


def _chave_reserva(aula: Aula) -> str:
    if aula.google_event_id:
        return f"google:{aula.google_event_id}"
    if aula.turma_id:
        return f"turma:{aula.turma_id}:{aula.data_inicio.isoformat()}"
    return f"aula:{aula.id}"


def contar_reservas_simultaneas(
    db: Session,
    inicio: datetime,
    fim: datetime,
    professor_id: Optional[int],
) -> int:
    query = db.query(Aula).filter(
        Aula.data_inicio < fim,
        Aula.data_fim > inicio,
        Aula.status.in_(STATUS_OCUPADOS),
    )
    if professor_id is None:
        query = query.filter(Aula.professor_id.is_(None))
    else:
        query = query.filter(Aula.professor_id == professor_id)

    return len({_chave_reserva(aula) for aula in query.all()})


def grade_aceita_horario(grade: GradeProfessor, inicio: datetime, fim: datetime) -> bool:
    try:
        hora_inicio = datetime.strptime(grade.hora_inicio, "%H:%M").time()
        hora_fim = datetime.strptime(grade.hora_fim, "%H:%M").time()
    except (TypeError, ValueError):
        return False

    return (
        bool(grade.ativo)
        and grade.dia_semana == inicio.weekday()
        and inicio.time() >= hora_inicio
        and fim.time() <= hora_fim
        and inicio.date() == fim.date()
    )


def resolver_grade_disponivel(
    db: Session,
    inicio: datetime,
    fim: datetime,
    grade_id_preferida: Optional[int] = None,
    bloquear: bool = False,
) -> Optional[GradeProfessor]:
    query = (
        db.query(GradeProfessor)
        .outerjoin(Professor, GradeProfessor.professor_id == Professor.id)
        .filter(
            GradeProfessor.dia_semana == inicio.weekday(),
            GradeProfessor.ativo.is_(True),
            (GradeProfessor.professor_id.is_(None)) | (Professor.ativo.is_(True)),
        )
    )
    if bloquear:
        query = query.with_for_update()

    grades = query.all()
    grades.sort(key=lambda grade: grade.id != grade_id_preferida)

    for grade in grades:
        if not grade_aceita_horario(grade, inicio, fim):
            continue
        ocupadas = contar_reservas_simultaneas(db, inicio, fim, grade.professor_id)
        if ocupadas < max(int(grade.capacidade or 1), 1):
            return grade
    return None
