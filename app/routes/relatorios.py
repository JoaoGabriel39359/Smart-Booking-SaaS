from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer

from app.database import get_db
from app.auth import verificar_token
from app.models import Aluno, Aula, HistoricoAula, StatusAula
from app.core.config import agora_br

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


@router.get("/frequencia")
def relatorio_frequencia(
    dias: int = Query(30, description="Período em dias para análise"),
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token)
):
    """
    Retorna a taxa de frequência e estatísticas por aluno baseando-se no HistoricoAula (chamada_realizada=True).
    """
    data_inicio = agora_br() - timedelta(days=dias)

    # 1. Consulta agrupadora de histórico pedagógico por aluno
    rows = db.query(
        Aluno.id,
        Aluno.nome,
        Aluno.sobrenome,
        func.count(HistoricoAula.id).label("total_aulas"),
        func.sum(func.cast(HistoricoAula.status_presenca == True, Integer)).label("presencas"),
        func.max(HistoricoAula.data_aula).label("ultima_aula")
    ).join(HistoricoAula, HistoricoAula.aluno_id == Aluno.id)\
     .filter(HistoricoAula.chamada_realizada == True, HistoricoAula.data_aula >= data_inicio)\
     .group_by(Aluno.id, Aluno.nome, Aluno.sobrenome).all()

    # 2. Contagem de cancelamentos no período por aluno
    cancelamentos_dict = dict(
        db.query(Aula.aluno_id, func.count(Aula.id))\
          .filter(Aula.status == StatusAula.cancelado, Aula.data_inicio >= data_inicio)\
          .group_by(Aula.aluno_id).all()
    )

    resultado = []
    for r in rows:
        aluno_id, nome, sobrenome, total, presencas, ultima_aula = r
        presencas = presencas or 0
        faltas = total - presencas
        canc = cancelamentos_dict.get(aluno_id, 0)
        taxa = round((presencas / total * 100), 1) if total > 0 else 0.0

        resultado.append({
            "aluno_id": aluno_id,
            "nome": f"{nome} {sobrenome or ''}".strip(),
            "total_aulas": total,
            "presencas": presencas,
            "faltas": faltas,
            "cancelamentos": canc,
            "taxa_presenca": taxa,
            "ultima_aula": ultima_aula.strftime("%d/%m/%Y") if ultima_aula else "-"
        })

    return resultado


@router.get("/cancelamentos-semana")
def cancelamentos_semana(
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token)
):
    """
    Retorna aulas canceladas nos últimos 7 dias.
    """
    limite = agora_br() - timedelta(days=7)
    aulas = db.query(Aula).join(Aluno).filter(
        Aula.status == StatusAula.cancelado,
        Aula.data_inicio >= limite
    ).order_by(Aula.data_inicio.desc()).all()

    resultado = []
    for a in aulas:
        aluno = a.aluno
        resultado.append({
            "aula_id": a.id,
            "aluno_id": a.aluno_id,
            "nome": f"{aluno.nome} {aluno.sobrenome or ''}".strip() if aluno else "Aluno",
            "telefone": aluno.telefone if aluno else "",
            "data_aula": a.data_inicio.strftime("%d/%m/%Y %H:%M"),
            "gerou_credito": a.validade_reposicao is not None,
            "validade_reposicao": a.validade_reposicao.strftime("%d/%m/%Y") if a.validade_reposicao else None
        })

    return resultado


@router.get("/creditos")
def relatorio_creditos(
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token)
):
    """
    Retorna alunos com créditos válidos a repor, atualizando Aluno.creditos_reposicao para garantir consistência.
    """
    agora = agora_br()
    alunos = db.query(Aluno).all()
    resultado = []

    for aluno in alunos:
        # Aulas canceladas validas no futuro
        aulas_validas = db.query(Aula).filter(
            Aula.aluno_id == aluno.id,
            Aula.status == StatusAula.cancelado,
            Aula.validade_reposicao >= agora
        ).order_by(Aula.validade_reposicao.asc()).all()

        qtd_validos = len(aulas_validas)

        # Sincroniza contador no modelo Aluno
        if aluno.creditos_reposicao != qtd_validos:
            aluno.creditos_reposicao = qtd_validos

        if qtd_validos > 0:
            validade_proxima = aulas_validas[0].validade_reposicao.strftime("%d/%m/%Y")

            vencidos = db.query(Aula).filter(
                Aula.aluno_id == aluno.id,
                Aula.status == StatusAula.cancelado,
                Aula.validade_reposicao < agora
            ).count()

            resultado.append({
                "aluno_id": aluno.id,
                "nome": f"{aluno.nome} {aluno.sobrenome or ''}".strip(),
                "telefone": aluno.telefone,
                "creditos_validos": qtd_validos,
                "validade_proxima": validade_proxima,
                "vencidos": vencidos
            })

    db.commit()
    return resultado
