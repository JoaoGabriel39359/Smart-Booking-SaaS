from fastapi import APIRouter, HTTPException, Depends  
from app.services.google_calendar import criar_evento as criar_evento_google
from sqlalchemy.orm import Session                     
from app.database import SessionLocal, get_db          
from app.models import Turma, Aluno, Aula                   
from .schemas import TurmaCreate 
from datetime import date, datetime, timedelta
import calendar
import re

router = APIRouter(prefix="/turmas", tags=["turmas"])

# ==========================================================
# FUNÇÃO AUXILIAR (A INCREMENTAÇÃO)
# ==========================================================
def processar_geracao_aulas(db: Session, turma: Turma):
    """Calcula as datas do mês e cria as aulas no banco e Google"""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    
    dias_map = {
        "Segunda": 0, "Terça": 1, "Quarta": 2, 
        "Quinta": 3, "Sexta": 4, "Sábado": 5, "Domingo": 6
    }
    
    dia_alvo = dias_map.get(turma.dia_semana)
    if dia_alvo is None:
        return 0

    cal = calendar.Calendar(firstweekday=0)
    aulas_criadas = 0

    # Itera sobre os dias do mês atual
    for dia in cal.itermonthdates(ano, mes):
        # Filtra: dia da semana correto, dentro do mês e não pode ser no passado
        if dia.weekday() == dia_alvo and dia.month == mes and dia >= hoje:
            
            hora_aula = datetime.strptime(turma.horario, "%H:%M").time()
            data_inicio = datetime.combine(dia, hora_aula)
            data_fim = data_inicio + timedelta(hours=1)
            
            for aluno in turma.alunos:
                # Verifica se a aula já existe para evitar duplicidade
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
                        tipo=turma.tipo
                    )
                    db.add(nova_aula)
                    db.flush() 

                    # Tenta sincronizar com Google Agenda
                    try:
                        nome_completo = f"{aluno.nome} {aluno.sobrenome or ''}".strip()
                        event_id = criar_evento_google(
                            inicio=data_inicio,
                            fim=data_fim,
                            nome_aluno=f"{turma.tipo}: {nome_completo}"
                        )
                        if event_id:
                            nova_aula.google_event_id = event_id
                    except Exception as g_error:
                        print(f"Erro Google Agenda: {g_error}")
                    
                    aulas_criadas += 1
    db.commit()
    return aulas_criadas

@router.post("/")
def criar_turma(dados: TurmaCreate):
    db = SessionLocal()
    try:
        # 1. DEFINIR LIMITES
        limites = {"VIP": 1, "DUO": 2, "TEAM": 6}
        limite_max = limites.get(dados.tipo, 6)

        # 2. VERIFICAR QUANTIDADE DE ALUNOS ENVIADOS
        if len(dados.aluno_ids) > limite_max:
            raise HTTPException(
                status_code=400, 
                detail=f"Você tentou colocar {len(dados.aluno_ids)} alunos, mas o limite para {dados.tipo} é {limite_max}."
            )

        # 3. CRIAÇÃO DA TURMA (Ajustado para os novos campos)
        nova_turma = Turma(
            nome_turma=dados.nome_turma, # Verifique se no Models.py está exatamente assim
            tipo=dados.tipo,
            dia_semana=dados.dia_semana,  # Recebe do JavaScript
            horario=dados.horario,        # Recebe do JavaScript
            capacidade_maxima=limite_max
        )
        db.add(nova_turma)
        db.flush() 

        # 4. VINCULA OS ALUNOS
        alunos = db.query(Aluno).filter(Aluno.id.in_(dados.aluno_ids)).all()
        for aluno in alunos:
            aluno.turma_id = nova_turma.id
            aluno.tipo = dados.tipo # Atualiza o tipo do aluno para bater com a turma

        db.commit()
        return {"msg": f"Turma {nova_turma.nome_turma} criada com sucesso para {dados.dia_semana}s às {dados.horario}!"}
        
    except HTTPException as http_e:
        db.rollback()
        raise http_e
    except Exception as e:
        db.rollback()
        # Esse detalhe str(e) vai te mostrar no console se houver erro de nome de coluna
        raise HTTPException(status_code=400, detail=f"Erro ao salvar no banco: {str(e)}")
    finally:
        db.close()

@router.post("/gerar-mensal")
def rota_gerar_mensal(db: Session = Depends(get_db)):
    """Rota manual caso queira forçar a atualização de todas as turmas"""
    turmas = db.query(Turma).all()
    total_geral = 0
    for t in turmas:
        total_geral += processar_geracao_aulas(db, t)
    return {"msg": f"Total de {total_geral} aulas sincronizadas no sistema."}

@router.get("/")
def listar_turmas(db: Session = Depends(get_db)):
    turmas = db.query(Turma).all()
    resultado = []
    
    for t in turmas:
        resultado.append({
            "id": t.id,
            "nome_turma": t.nome_turma,  # <--- ALTERE DE t.nome PARA t.nome_turma
            "tipo": t.tipo,
            "dia_semana": t.dia_semana,
            "horario": t.horario,
            "capacidade_maxima": t.capacidade_maxima,
            "alunos": [
                {"id": a.id, "nome": a.nome, "sobrenome": a.sobrenome} 
                for a in t.alunos
            ]
        })
    return resultado

@router.delete("/{turma_id}")
def deletar_turma(turma_id: int):
    db = SessionLocal()
    try:
        # 1. Busca a turma para ter certeza que existe
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        # 2. LIMPEZA DOS ALUNOS: Desvincula os alunos (seta turma_id como null)
        # Isso evita que o aluno seja deletado, apenas "tira ele da sala"
        db.query(Aluno).filter(Aluno.turma_id == turma_id).update({"turma_id": None})
        
        # 3. LIMPEZA DAS AULAS: Deleta todas as aulas associadas a essa turma
        # Isso resolve o erro "ForeignKeyViolation" que travou seu código
        db.query(Aula).filter(Aula.turma_id == turma_id).delete()
        
        # 4. DELETAR A TURMA: Agora que não há mais aulas ligadas a ela, podemos apagar
        db.delete(turma)
        
        db.commit()
        return {"msg": "Turma e aulas deletadas com sucesso. Alunos permanecem no banco (sem turma)."}
        
    except Exception as e:
        db.rollback()
        print(f"Erro ao deletar turma: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    finally:
        db.close()

@router.post("/{turma_id}/adicionar-aluno/{aluno_id}")
def adicionar_aluno_turma(turma_id: int, aluno_id: int, db: Session = Depends(get_db)):
    # Remova o "models." e use apenas Turma e Aluno
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()

    if not turma or not aluno:
        raise HTTPException(status_code=404, detail="Turma ou Aluno não encontrado")

    # Regra de Limite
    limites = {"VIP": 1, "DUO": 2, "TEAM": 6}
    total_atual = len(turma.alunos)

    # Pegamos o limite com base no tipo, padrão é 1 se não encontrar
    limite_permitido = limites.get(turma.tipo, 1)

    if total_atual >= limite_permitido:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite de {turma.tipo} atingido ({limite_permitido} alunos)."
        )

    aluno.turma_id = turma_id
    # Opcional: garantir que o tipo do aluno acompanhe o da turma
    #aluno.tipo = turma.tipo 
    
    db.commit()
    return {"msg": f"{aluno.nome} adicionado à turma {turma.nome_turma} com sucesso!"}

@router.post("/{turma_id}/remover-aluno/{aluno_id}")
def remover_aluno_turma(turma_id: int, aluno_id: int, db: Session = Depends(get_db)):
    # Procuramos o aluno que pertence a essa turma específica
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id, Aluno.turma_id == turma_id).first()

    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado nesta turma.")

    # Removemos o vínculo
    aluno.turma_id = None
    # Opcional: Se quiseres que ele volte a ser "VIP" por padrão ao sair de uma turma
    # aluno.tipo = "VIP" 

    db.commit()
    return {"msg": f"{aluno.nome} removido da turma com sucesso!"}

@router.post("/gerar-mensal")
def gerar_aulas_mes():
    db = SessionLocal()
    try:
        hoje = date.today()
        ano, mes = hoje.year, hoje.month
        turmas = db.query(Turma).all()
        aulas_criadas = 0
        dias_map = {"Segunda": 0, "Terça": 1, "Quarta": 2, "Quinta": 3, "Sexta": 4, "Sábado": 5, "Domingo": 6}

        for turma in turmas:
            dia_alvo = dias_map.get(turma.dia_semana)
            if dia_alvo is None: continue

            cal = calendar.Calendar(firstweekday=0)
            for dia in cal.itermonthdates(ano, mes):
                if dia.weekday() == dia_alvo and dia.month == mes and dia >= hoje:
                    
                    hora_aula = datetime.strptime(turma.horario, "%H:%M").time()
                    data_inicio = datetime.combine(dia, hora_aula)
                    data_fim = data_inicio + timedelta(hours=1)

                    # --- PASSO 1: GERAR O ID ÚNICO ---
                    # Esta variável DEVE ser preenchida apenas UMA VEZ por horário
                    ID_UNICO_PARA_ESTE_HORARIO = None
                    
                    try:
                        nome_evento = f"{turma.tipo}: {turma.nome_turma}"
                        # CHAMADA AO GOOGLE
                        ID_UNICO_PARA_ESTE_HORARIO = criar_evento_google(data_inicio, data_fim, nome_evento)
                        print(f"\n[Sincronizador] Criado no Google ID: {ID_UNICO_PARA_ESTE_HORARIO} para a data {dia}")
                    except Exception as g_error:
                        print(f"[Erro Google]: {g_error}")

                    # --- PASSO 2: DISTRIBUIR O MESMO ID PARA TODOS OS ALUNOS ---
                    for aluno in turma.alunos:
                        print(f"[Sincronizador] Vinculando Aluno {aluno.nome} ao ID: {ID_UNICO_PARA_ESTE_HORARIO}")
                        
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
                                tipo=turma.tipo,
                                google_event_id=ID_UNICO_PARA_ESTE_HORARIO # <--- GARANTINDO O MESMO ID
                            )
                            db.add(nova_aula)
                            aulas_criadas += 1
                    
                    db.flush()

        db.commit()
        return {"msg": f"Sucesso! {aulas_criadas} aulas geradas."}
    except Exception as e:
        db.rollback()
        print(f"ERRO: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()