from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from app.services.whatsapp import enviar_boas_vindas_whatsapp
from app.database import SessionLocal, get_db
from sqlalchemy.orm import Session
from app.models import Aluno, Turma
from .schemas import AlunoCreate, AlunoEdit
import re
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/alunos", tags=["alunos"])

def padronizar_telefone(telefone: str) -> str:
    tel_limpo = re.sub(r"\D", "", telefone)
    if len(tel_limpo) == 11:
        return f"55{tel_limpo}"
    return tel_limpo

# --- ROTAS ---

# CRIAR ALUNO
@router.post("/")
def criar_aluno(dados: AlunoCreate):
    db = SessionLocal()
    if dados.turma_id:
        turma = db.query(Turma).filter(Turma.id == dados.turma_id).first()
        if not turma:
            db.close()
            raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    tel_final = padronizar_telefone(dados.telefone)
    novo = Aluno(
        nome=dados.nome, 
        sobrenome=dados.sobrenome,
        telefone=tel_final, 
        email=dados.email, 
        turma_id=dados.turma_id,
        tipo=dados.tipo,
        endereco=dados.endereco,
        cidade=dados.cidade,
        estado=dados.estado,
        limite_aulas_semana=2 
    )
    
    try:
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return {"msg": f"Aluno {novo.nome} cadastrado com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao salvar: {str(e)}")
    finally:
        db.close()

# LISTAR ALUNOS
@router.get("/")
def listar_alunos():
    db = SessionLocal()
    alunos = db.query(Aluno).all()
    db.close()
    return alunos

# EDITAR ALUNO (APENAS UMA VERSÃO, A COMPLETA)
@router.put("/{aluno_id}")
def editar_aluno(aluno_id: int, dados: AlunoEdit, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    try:
        # Atualiza apenas o que foi enviado (evita sobrescrever com None)
        aluno.nome = dados.nome or aluno.nome
        aluno.sobrenome = dados.sobrenome or aluno.sobrenome
        aluno.telefone = padronizar_telefone(dados.telefone) if dados.telefone else aluno.telefone
        aluno.email = dados.email or aluno.email
        aluno.endereco = dados.endereco or aluno.endereco
        aluno.cidade = dados.cidade or aluno.cidade
        aluno.estado = dados.estado or aluno.estado

        # SÓ ALTERA O TIPO SE VIER ALGO NO PAYLOAD E FOR DIFERENTE DE NONE
        if dados.tipo is not None:
            aluno.tipo = dados.tipo 

        db.commit()
        db.refresh(aluno)
        return {"msg": "Dados atualizados com sucesso!"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar: {str(e)}")
    
# DELETAR ALUNO
@router.delete("/{aluno_id}")
def deletar_aluno(aluno_id: int):
    db = SessionLocal()
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        db.close()
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    db.delete(aluno)
    db.commit()
    db.close()
    return {"msg": "Aluno deletado com sucesso"}

@router.get("/sem-turma")
def listar_alunos_sem_turma(db: Session = Depends(get_db)):
    # Retorna apenas alunos que o turma_id é nulo
    return db.query(Aluno).filter(Aluno.turma_id == None).all()

@router.get("/portal/{aluno_id}", response_class=HTMLResponse)
def portal_do_aluno(aluno_id: int, db: Session = Depends(get_db)):
    # Busca o aluno no banco para confirmar que o ID é válido
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    
    if not aluno:
        return "<h1>Aluno não encontrado</h1>"

    # Retorna um HTML simples para o celular do aluno
    return f"""
    <html>
        <head>
            <title>Portal do Aluno</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: sans-serif; text-align: center; padding: 50px; background-color: #f4f4f9; }}
                .card {{ background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; }}
                button {{ background: #27ae60; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Olá, {aluno.nome}! 👋</h1>
                <p>Você acessou seu portal de agendamento VIP.</p>
                <p>Seus créditos de reposição aparecem aqui embaixo:</p>
                <hr>
                <button>Agendar Reposição</button>
            </div>
        </body>
    </html>
    """