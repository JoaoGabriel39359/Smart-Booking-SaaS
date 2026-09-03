from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.auth import verificar_token
from app.models import Professor, GradeProfessor, Turma, Aula, StatusAula
from app.core.config import agora_br
from .schemas import ProfessorCreate, ProfessorEdit, ProfessorResponse

router = APIRouter(prefix="/professores", tags=["professores"])


@router.get("/", response_model=List[ProfessorResponse])
def listar_professores(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    professores = db.query(Professor).all()
    resultado = []

    for p in professores:
        turnos_count = db.query(GradeProfessor).filter(GradeProfessor.professor_id == p.id).count()
        turmas_count = db.query(Turma).filter(Turma.professor_id == p.id).count()

        resultado.append(ProfessorResponse(
            id=p.id,
            nome=p.nome,
            telefone=p.telefone,
            cor=p.cor,
            ativo=p.ativo,
            total_turnos=turnos_count,
            total_turmas=turmas_count
        ))

    return resultado


@router.post("/", response_model=ProfessorResponse)
def criar_professor(dados: ProfessorCreate, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    novo_professor = Professor(
        nome=dados.nome,
        telefone=dados.telefone,
        cor=dados.cor,
        ativo=dados.ativo
    )
    db.add(novo_professor)
    db.commit()
    db.refresh(novo_professor)

    return ProfessorResponse(
        id=novo_professor.id,
        nome=novo_professor.nome,
        telefone=novo_professor.telefone,
        cor=novo_professor.cor,
        ativo=novo_professor.ativo,
        total_turnos=0,
        total_turmas=0
    )


@router.put("/{id}", response_model=ProfessorResponse)
def editar_professor(id: int, dados: ProfessorEdit, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    professor = db.query(Professor).filter(Professor.id == id).first()
    if not professor:
        raise HTTPException(status_code=404, detail="Professor não encontrado")

    campos = dados.model_dump(exclude_unset=True)
    for campo, valor in campos.items():
        setattr(professor, campo, valor)

    db.commit()
    db.refresh(professor)

    turnos_count = db.query(GradeProfessor).filter(GradeProfessor.professor_id == professor.id).count()
    turmas_count = db.query(Turma).filter(Turma.professor_id == professor.id).count()

    return ProfessorResponse(
        id=professor.id,
        nome=professor.nome,
        telefone=professor.telefone,
        cor=professor.cor,
        ativo=professor.ativo,
        total_turnos=turnos_count,
        total_turmas=turmas_count
    )


@router.delete("/{id}")
def deletar_professor(id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    professor = db.query(Professor).filter(Professor.id == id).first()
    if not professor:
        raise HTTPException(status_code=404, detail="Professor não encontrado")

    agora = agora_br()
    aulas_futuras = db.query(Aula).filter(
        Aula.professor_id == id,
        Aula.data_inicio >= agora,
        Aula.status == StatusAula.marcada
    ).count()

    if aulas_futuras > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir o professor {professor.nome} pois existem {aulas_futuras} aula(s) futura(s) vinculada(s). Em vez de excluir, desative o cadastro (ativo=false)."
        )

    db.delete(professor)
    db.commit()
    return {"msg": f"Professor {professor.nome} excluído com sucesso"}
