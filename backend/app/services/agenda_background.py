from collections.abc import Iterable
from datetime import datetime

from app.database import SessionLocal
from app.models import Aula, HistoricoAula, StatusAula
from app.services import google_calendar
from app.services.gerar_agenda import gerar_aulas_da_semana


def _eventos_unicos(event_ids: Iterable[str | None]) -> list[str]:
    return list(dict.fromkeys(str(event_id) for event_id in event_ids if event_id))


def remover_eventos_google_sem_referencia(event_ids: Iterable[str | None]) -> None:
    """Remove eventos antigos somente quando nenhuma aula ativa ainda os utiliza."""
    ids = _eventos_unicos(event_ids)
    if not ids:
        return

    db = SessionLocal()
    try:
        for event_id in ids:
            ainda_em_uso = db.query(Aula.id).filter(
                Aula.google_event_id == event_id,
                Aula.status.in_([StatusAula.marcada, StatusAula.presente]),
            ).first()
            if ainda_em_uso:
                continue
            google_calendar.remover_evento_google(event_id)
    except Exception as exc:
        print(f"Falha ao limpar eventos antigos do Google Calendar: {exc}")
    finally:
        db.close()


def sincronizar_agenda_turma(
    turma_id: int,
    event_ids_removidos: Iterable[str | None] = (),
) -> None:
    """Sincroniza uma única turma sem manter a resposta HTTP bloqueada."""
    remover_eventos_google_sem_referencia(event_ids_removidos)
    try:
        gerar_aulas_da_semana(turma_id=turma_id)
    except Exception as exc:
        print(f"Falha ao sincronizar a agenda da turma {turma_id}: {exc}")


def sincronizar_agenda_completa() -> None:
    """Executa a geração mensal completa como tarefa de segundo plano."""
    try:
        gerar_aulas_da_semana()
    except Exception as exc:
        print(f"Falha ao sincronizar a agenda completa: {exc}")


def sincronizar_evento_aulas(
    aula_ids: Iterable[int],
    inicio: datetime,
    fim: datetime,
    titulo: str,
    meet_link_existente: str | None = None,
) -> None:
    """Cria o evento externo e associa seu ID às aulas já persistidas."""
    ids = list(dict.fromkeys(int(aula_id) for aula_id in aula_ids))
    if not ids:
        return

    try:
        resultado = google_calendar.criar_evento(
            inicio,
            fim,
            titulo,
            meet_link_existente=meet_link_existente,
        )
        event_id = resultado[0] if isinstance(resultado, tuple) else resultado
    except Exception as exc:
        print(f"Falha ao criar evento no Google Calendar: {exc}")
        return

    if not event_id:
        return

    db = SessionLocal()
    try:
        aulas = db.query(Aula).filter(
            Aula.id.in_(ids),
            Aula.status == StatusAula.marcada,
        ).all()
        if not aulas:
            google_calendar.remover_evento_google(event_id)
            return

        ids_existentes = []
        for aula in aulas:
            aula.google_event_id = str(event_id)
            ids_existentes.append(aula.id)

        db.query(HistoricoAula).filter(
            HistoricoAula.aula_id.in_(ids_existentes)
        ).update(
            {"google_event_id": str(event_id)},
            synchronize_session=False,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"Falha ao vincular evento do Google às aulas {ids}: {exc}")
        google_calendar.remover_evento_google(event_id)
    finally:
        db.close()
