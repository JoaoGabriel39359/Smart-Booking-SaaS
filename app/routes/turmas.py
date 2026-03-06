from fastapi import APIRouter, HTTPException, Depends  
from app import models
from app.auth import verificar_token
from app.services.google_calendar import criar_evento as criar_evento_google, remover_evento_google, criar_evento
from app.services.gerar_agenda import gerar_aulas_da_semana
from sqlalchemy.orm import Session                     
from app.database import get_db          
from app.models import Turma, Aluno, Aula, HorarioAula                
from datetime import date, datetime, timedelta
import calendar

router = APIRouter(prefix="/turmas", tags=["turmas"])

# ==========================================================
# FUNÇÃO AUXILIAR (A INCREMENTAÇÃO)
# ==========================================================

def processar_geracao_aulas(db: Session, turma: Turma):
    """Gera aulas para os próximos 30 dias a partir de hoje"""
    hoje = date.today()
    fim_periodo = hoje + timedelta(days=30)
    
    dias_map = {
        "Segunda": 0, "Terça": 1, "Quarta": 2, 
        "Quinta": 3, "Sexta": 4, "Sábado": 5, "Domingo": 6
    }
    
    dia_alvo = dias_map.get(turma.dia_semana)
    if dia_alvo is None:
        return 0

    aulas_criadas = 0
    data_atual = hoje

    while data_atual <= fim_periodo:
        if data_atual.weekday() == dia_alvo:
            hora_aula = datetime.strptime(turma.horario, "%H:%M").time()
            data_inicio = datetime.combine(data_atual, hora_aula)
            data_fim = data_inicio + timedelta(hours=1)

            google_id = None
            try:
                titulo_google = f"Turma {turma.tipo}: {turma.nome_turma}"
                google_id = criar_evento(data_inicio, data_fim, titulo_google)
                print(f"✅ Sincronizado no Google: {data_inicio}")
            except Exception as g_error:
                print(f"❌ Erro Google Agenda: {g_error}")

            for aluno in turma.alunos:
                existe = db.query(Aula).filter(
                    Aula.aluno_id == aluno.id, 
                    Aula.data_inicio == data_inicio
                ).first()
                
                if not existe:
                    nova_aula = Aula(
                        aluno_id=aluno.id,
                        turma_id=turma.id,
                        data_inicio=data_inicio,
                        data_fim=data_fim,
                        status="marcada",
                        google_event_id=google_id
                    )
                    db.add(nova_aula)
                    aulas_criadas += 1
            db.flush() 
            
        data_atual += timedelta(days=1)
    db.commit()
    return aulas_criadas

# --- CRIAR TURMA ---
@router.post("/")
def criar_turma(dados: dict, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        limites = {"VIP": 1, "DUO": 2, "TEAM": 6}
        limite_max = limites.get(dados.get('tipo'), 6)

        if len(dados.get('aluno_ids', [])) > limite_max:
            raise HTTPException(status_code=400, detail="Limite de alunos excedido.")

        nova_turma = Turma(
            nome_turma=dados.get('nome_turma'),
            tipo=dados.get('tipo'),
            duracao_minutos=int(dados.get('duracao_minutos', 60)),
            capacidade_maxima=limite_max
        )
        db.add(nova_turma)
        db.flush() 

        for h in dados.get('horarios', []):
            novo_h = HorarioAula(
                turma_id=nova_turma.id,
                dia_da_semana=int(h['dia']),
                horario=datetime.strptime(h['hora'], "%H:%M").time()
            )
            db.add(novo_h)

        alunos = db.query(Aluno).filter(Aluno.id.in_(dados.get('aluno_ids', []))).all()
        for aluno in alunos:
            aluno.turma_id = nova_turma.id
            aluno.tipo = dados.get('tipo')

        db.commit()
        gerar_aulas_da_semana(db) 
        return {"msg": f"Turma {nova_turma.nome_turma} criada e aulas sincronizadas!"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# --- GERAR MENSAL (VERSÃO UNIFICADA) ---
@router.post("/gerar-mensal")
def rota_gerar_mensal(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        gerar_aulas_da_semana(db)
        return {"msg": "Agenda do mês e Google Calendar sincronizados com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar: {str(e)}")

# --- LISTAR TURMAS ---
@router.get("/")
def listar_turmas(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    turmas = db.query(Turma).all()
    resultado = []
    for t in turmas:
        resultado.append({
            "id": t.id,
            "nome_turma": t.nome_turma,
            "tipo": t.tipo,
            "dia_semana": t.dia_semana,
            "horario": t.horario,
            "capacidade_maxima": t.capacidade_maxima,
            "alunos": [{"id": a.id, "nome": a.nome, "sobrenome": a.sobrenome} for a in t.alunos]
        })
    return resultado

# --- DELETAR TURMA ---
@router.delete("/{turma_id}")
def deletar_turma(turma_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        aulas_com_google = db.query(models.HistoricoAula.google_event_id).filter(
            models.HistoricoAula.aluno.has(turma_id=turma_id),
            models.HistoricoAula.google_event_id != None
        ).distinct().all()

        for (g_id,) in aulas_com_google:
            try:
                remover_evento_google(g_id)
            except:
                pass

        db.query(models.Aluno).filter(models.Aluno.turma_id == turma_id).update({"turma_id": None})
        db.query(models.HistoricoAula).filter(models.HistoricoAula.aluno.has(turma_id=turma_id)).delete(synchronize_session=False)

        db.delete(turma)
        db.commit()
        return {"msg": "Turma e agenda do Google limpas com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- ADICIONAR ALUNO ---
@router.post("/{turma_id}/adicionar-aluno/{aluno_id}")
def adicionar_aluno_turma(turma_id: int, aluno_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not turma or not aluno:
        raise HTTPException(status_code=404, detail="Não encontrado")
    
    if len(turma.alunos) >= ({"VIP": 1, "DUO": 2, "TEAM": 6}.get(turma.tipo, 1)):
        raise HTTPException(status_code=400, detail="Limite atingido.")

    aluno.turma_id = turma_id
    db.commit()
    return {"msg": f"{aluno.nome} adicionado!"}

# --- REMOVER ALUNO ---
@router.post("/{turma_id}/remover-aluno/{aluno_id}")
def remover_aluno_turma(turma_id: int, aluno_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id, Aluno.turma_id == turma_id).first()
    if not aluno:
        raise HTTPException(status_code=404)
    aluno.turma_id = None
    db.commit()
    return {"msg": "Removido!"}