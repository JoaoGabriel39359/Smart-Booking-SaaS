import uuid
import re
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import verificar_token
from app.models import Aluno, Aula, HistoricoAula, Turma, StatusAula
from app.core.config import BASE_URL
from app.services.whatsapp import enviar_whatsapp
from app.services.creditos import ajustar_creditos_manualmente
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
    creditos_solicitados = campos_para_atualizar.pop("creditos_reposicao", None)

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

        if creditos_solicitados is not None:
            ajustar_creditos_manualmente(db, aluno, int(creditos_solicitados))

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
def obter_relatorio_aluno(
    aluno_id: int,
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    historico = db.query(HistoricoAula).filter(
        HistoricoAula.aluno_id == aluno_id,
        HistoricoAula.chamada_realizada.is_(True),
    ).order_by(HistoricoAula.data_aula.desc()).all()
    aulas_finalizadas = db.query(Aula).filter(
        Aula.aluno_id == aluno_id,
        Aula.status.in_([StatusAula.presente, StatusAula.ausente]),
    ).order_by(Aula.data_inicio.desc()).all()

    registros = {}
    for item in historico:
        aula = item.aula
        if aula and aula.status == StatusAula.cancelado:
            continue
        if not aula and "cancelad" in (item.observacao or "").lower():
            continue
        chave = f"aula:{item.aula_id}" if item.aula_id else f"historico:{item.id}"
        registros[chave] = {
            "id": item.id,
            "data_inicio": item.data_aula.isoformat(),
            "presente": bool(item.status_presenca),
            "status": "Presente" if item.status_presenca else "Ausente",
            "desempenho": item.desempenho or (aula.desempenho if aula else None) or "Sem avaliação",
            "observacao": item.observacao or (aula.observacoes if aula else None) or "-",
            "turma": aula.turma.nome_turma if aula and aula.turma else None,
            "professor": aula.professor.nome if aula and aula.professor else None,
            "eh_reposicao": bool(aula.eh_reposicao) if aula else False,
        }

    for aula in aulas_finalizadas:
        chave = f"aula:{aula.id}"
        if chave in registros:
            continue
        presente = aula.status == StatusAula.presente
        registros[chave] = {
            "id": aula.id,
            "data_inicio": aula.data_inicio.isoformat(),
            "presente": presente,
            "status": "Presente" if presente else "Ausente",
            "desempenho": aula.desempenho or "Sem avaliação",
            "observacao": aula.observacoes or "-",
            "turma": aula.turma.nome_turma if aula.turma else None,
            "professor": aula.professor.nome if aula.professor else None,
            "eh_reposicao": bool(aula.eh_reposicao),
        }

    lista = sorted(registros.values(), key=lambda registro: registro["data_inicio"], reverse=True)
    presencas = sum(1 for registro in lista if registro["presente"])
    total = len(lista)
    return {
        "aluno": {
            "id": aluno.id,
            "nome": f"{aluno.nome} {aluno.sobrenome or ''}".strip(),
            "tipo": aluno.tipo.value if hasattr(aluno.tipo, "value") else str(aluno.tipo),
            "turma": aluno.turma.nome_turma if aluno.turma else None,
        },
        "resumo": {
            "total_aulas": total,
            "presencas": presencas,
            "faltas": total - presencas,
            "taxa_presenca": round((presencas / total) * 100, 1) if total else 0,
        },
        "registros": lista,
    }
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
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    if not aluno.token_acesso:
        aluno.token_acesso = str(uuid.uuid4())
        db.commit()
        db.refresh(aluno)

    if BASE_URL.startswith(("http://127.0.0.1", "http://localhost", "http://0.0.0.0")):
        raise HTTPException(
            status_code=400,
            detail="O BASE_URL está local. Use a URL pública do Render para enviar um link acessível ao aluno.",
        )

    link = f"{BASE_URL}/portal/{aluno.token_acesso}"
    mensagem = (
        f"Olá, {aluno.nome}! 👋\n\n"
        "Aqui está o seu link de acesso exclusivo ao portal de agendamentos:\n\n"
        f"{link}\n\n"
        "Por lá você pode consultar suas aulas e agendar reposições."
    )
    if not enviar_whatsapp(aluno.telefone, mensagem):
        raise HTTPException(
            status_code=502,
            detail="A Evolution não aceitou a mensagem. Verifique se a instância configurada existe e está conectada.",
        )
    return {"status": "enviado", "mensagem": "Link enviado pelo WhatsApp."}
