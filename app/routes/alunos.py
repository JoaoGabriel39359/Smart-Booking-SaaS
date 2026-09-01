import uuid
import re
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import verificar_token
from app.models import Aluno, Aula, HistoricoAula, Turma
from app.core.config import BASE_URL
from app.services.whatsapp import enviar_whatsapp
from .schemas import AlunoCreate, AlunoEdit

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

    campos_para_atualizar = dados.model_dump(exclude_unset=True)

    # Validação de capacidade se turma_id for alterado
    if "turma_id" in campos_para_atualizar:
        nova_turma_id = campos_para_atualizar["turma_id"]
        if nova_turma_id is not None and nova_turma_id != aluno.turma_id:
            turma_destino = db.query(Turma).filter(Turma.id == nova_turma_id).first()
            if not turma_destino:
                raise HTTPException(status_code=404, detail="Turma destino não encontrada")

            limites = {"VIP": 1, "DUO": 2, "TEAM": 6}
            capacidade_max = limites.get(turma_destino.tipo, turma_destino.capacidade_maxima or 6)

            alunos_na_turma = db.query(Aluno).filter(Aluno.turma_id == nova_turma_id, Aluno.id != aluno_id).count()
            if alunos_na_turma >= capacidade_max:
                raise HTTPException(
                    status_code=400, 
                    detail=f"A turma {turma_destino.nome_turma} atingiu a capacidade máxima ({capacidade_max} alunos)."
                )

    try:
        for campo, valor in campos_para_atualizar.items():
            if campo == "telefone" and valor is not None:
                aluno.telefone = padronizar_telefone(valor)
            else:
                setattr(aluno, campo, valor)

        db.commit()
        db.refresh(aluno)
        return {"msg": "Dados atualizados com sucesso!"}
    except HTTPException as http_e:
        db.rollback()
        raise http_e
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

@router.get("/{aluno_id}/relatorio")
def obter_relatorio_aluno(aluno_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    # 1. Busca dados da tabela HistoricoAula onde a chamada já foi concluída
    historico = db.query(HistoricoAula).filter(
        HistoricoAula.aluno_id == aluno_id,
        HistoricoAula.chamada_realizada == True # Só o que foi finalizado aparece aqui
    ).order_by(HistoricoAula.data_aula.desc()).all()
    
    # 2. Busca dados da tabela Aula (Backup para casos onde o status mudou mas o histórico falhou)
    aulas_passadas = db.query(Aula).filter(
        Aula.aluno_id == aluno_id,
        Aula.status.in_(["Presente", "Ausente"]) # Use os valores do seu Enum StatusAula
    ).order_by(Aula.data_inicio.desc()).all()

    relatorio_final = []

    # Processamento do Histórico Pedagógico
    for h in historico:
        relatorio_final.append({
            "data": h.data_aula.strftime("%d/%m/%Y") if h.data_aula else "Data N/A",
            "presenca": "✅ Presente" if h.status_presenca else "❌ Falta",
            "desempenho": h.desempenho or "Sem avaliação",
            "observacao": h.observacao or "-"
        })

    # Evita duplicidade se a aula estiver nas duas tabelas
    datas_no_relatorio = {r["data"] for r in relatorio_final}

    for a in aulas_passadas:
        data_str = a.data_inicio.strftime("%d/%m/%Y")
        if data_str not in datas_no_relatorio:
            relatorio_final.append({
                "data": data_str,
                "presenca": "✅ Presente" if a.status.value == "Presente" else "❌ Falta",
                "desempenho": "Aguardando avaliação",
                "observacao": "-"
            })

    return relatorio_final


# --- GERENCIAMENTO DE LINK DO PORTAL ---

@router.post("/regerar-tokens")
def regerar_tokens_alunos(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    alunos_sem_token = db.query(Aluno).filter((Aluno.token_acesso == None) | (Aluno.token_acesso == "")).all()
    count = 0
    for a in alunos_sem_token:
        a.token_acesso = str(uuid.uuid4())
        count += 1
    if count > 0:
        db.commit()
    return {"corrigidos": count}


@router.get("/{aluno_id}/link-portal")
def obter_link_portal(aluno_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    if not aluno.token_acesso:
        aluno.token_acesso = str(uuid.uuid4())
        db.commit()
        db.refresh(aluno)

    return {"link": f"{BASE_URL}/portal/{aluno.token_acesso}"}


@router.post("/{aluno_id}/enviar-portal")
def enviar_link_portal_whatsapp(
    aluno_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    if not aluno.token_acesso:
        aluno.token_acesso = str(uuid.uuid4())
        db.commit()
        db.refresh(aluno)

    link = f"{BASE_URL}/portal/{aluno.token_acesso}"
    mensagem = (
        f"Olá, {aluno.nome}! 👋\n\n"
        f"Aqui está o seu link de acesso exclusivo ao portal de agendamentos:\n\n"
        f"{link}\n\n"
        f"Por lá você pode consultar suas aulas, agendar reposições e muito mais!"
    )
    background_tasks.add_task(enviar_whatsapp, aluno.telefone, mensagem)
    return {"status": "enviado"}