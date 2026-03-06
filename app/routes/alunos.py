from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from app.database import get_db  # Importamos apenas o necessário
from app.auth import verificar_token
from sqlalchemy.orm import Session
from app.models import Aluno, HistoricoAula, Turma
from .schemas import AlunoCreate, AlunoEdit
import re

router = APIRouter(prefix="/alunos", tags=["alunos"])

def padronizar_telefone(telefone: str) -> str:
    tel_limpo = re.sub(r"\D", "", telefone)
    if len(tel_limpo) == 11:
        return f"55{tel_limpo}"
    return tel_limpo

# --- ROTAS ---

# CRIAR ALUNO
@router.post("/")
def criar_aluno(dados: AlunoCreate, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    if dados.turma_id:
        turma = db.query(Turma).filter(Turma.id == dados.turma_id).first()
        if not turma:
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

# LISTAR ALUNOS
@router.get("/")
def listar_alunos(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    return db.query(Aluno).all()

# EDITAR ALUNO
@router.put("/{aluno_id}")
def editar_aluno(aluno_id: int, dados: AlunoEdit, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    try:
        aluno.nome = dados.nome or aluno.nome
        aluno.sobrenome = dados.sobrenome or aluno.sobrenome
        aluno.telefone = padronizar_telefone(dados.telefone) if dados.telefone else aluno.telefone
        aluno.email = dados.email or aluno.email
        aluno.endereco = dados.endereco or aluno.endereco
        aluno.cidade = dados.cidade or aluno.cidade
        aluno.estado = dados.estado or aluno.estado

        if dados.tipo is not None:
            aluno.tipo = dados.tipo 

        db.commit()
        db.refresh(aluno)
        return {"msg": "Dados atualizados com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar: {str(e)}")
    
# DELETAR ALUNO
@router.delete("/{id}")
def deletar_aluno(id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    db.delete(aluno)
    db.commit()
    return {"message": "Aluno removido com sucesso"}

@router.get("/sem-turma")
def listar_alunos_sem_turma(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    return db.query(Aluno).filter(Aluno.turma_id == None).all()

# PORTAL DO ALUNO (Mantendo seu HTML 100% original)
@router.get("/portal/{aluno_id}", response_class=HTMLResponse)
def portal_do_aluno(aluno_id: int, db: Session = Depends(get_db)):
    # 1. Busca o aluno
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    
    if not aluno:
        return "<h1>Aluno não encontrado</h1>"

    # 2. Busca as aulas (Incluindo o status 'marcada' para ele ver o que tem hoje/futuro)
    aulas = db.query(Aula).filter(
        Aula.aluno_id == aluno.id,
        Aula.status.in_(['marcada', 'presente', 'confirmada'])
    ).order_by(Aula.data_inicio.asc()).all()

    # 3. Monta a lista de aulas em HTML
    aulas_html = ""
    if not aulas:
        aulas_html = "<p style='color: #94a3b8;'>Nenhuma aula agendada no momento.</p>"
    else:
        for aula in aulas:
            data_fmt = aula.data_inicio.strftime('%d/%m às %H:%M')
            status_label = "✅ Confirmada" if aula.status == 'marcada' else "⭐ Aula"
            aulas_html += f"""
                <div style="background: #f8fafc; padding: 12px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #4f46e5; text-align: left;">
                    <strong style="display: block; color: #1e293b;">{data_fmt}</strong>
                    <span style="font-size: 11px; color: #6366f1; font-weight: bold;">{status_label}</span>
                </div>
            """

    # 4. Retorna o HTML final com os dados inseridos
    return f"""
    <html>
        <head>
            <title>Portal do Aluno - One School</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: sans-serif; text-align: center; padding: 20px; background-color: #f4f4f9; color: #334155; }}
                .card {{ background: white; padding: 30px; border-radius: 25px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); max-width: 400px; margin: auto; }}
                h1 {{ color: #1e293b; font-size: 24px; margin-bottom: 5px; }}
                .creditos {{ background: #eef2ff; color: #4f46e5; padding: 10px; border-radius: 12px; font-weight: bold; margin: 20px 0; }}
                .lista-aulas {{ margin-top: 25px; }}
                button {{ background: #4f46e5; color: white; border: none; padding: 15px 25px; border-radius: 15px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 20px; }}
                hr {{ border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Olá, {aluno.nome}! 👋</h1>
                <p style="font-size: 14px; color: #64748b;">Seu portal VIP de agendamentos</p>
                
                <div class="creditos">
                    Créditos de Reposição: {aluno.creditos_reposicao}
                </div>

                <div class="lista-aulas">
                    <h3 style="text-align: left; font-size: 16px;">📅 Minhas Aulas</h3>
                    {aulas_html}
                </div>

                <hr>
                <button onclick="alert('Funcionalidade de agendamento em breve no mobile!')">Agendar Reposição</button>
            </div>
        </body>
    </html>
    """

@router.get("/{aluno_id}/relatorio")
def obter_relatorio_aluno(aluno_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    historico = db.query(HistoricoAula).filter(
        HistoricoAula.aluno_id == aluno_id
    ).order_by(HistoricoAula.data_aula.desc()).all()
    
    return [
        {{
            "data": h.data_aula.strftime("%d/%m/%Y"),
            "presenca": "✅" if h.status_presenca else "❌",
            "desempenho": h.desempenho or "Sem avaliação",
            "observacao": h.observacao or "-"
        }} for h in historico
    ]