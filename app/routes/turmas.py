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

    # Inicializamos o link com o que está gravado na turma (se houver)
    link_meet_da_turma = turma.meet_link 

    while data_atual <= fim_periodo:
        if data_atual.weekday() == dia_alvo:
            hora_aula = datetime.strptime(turma.horario, "%H:%M").time()
            data_inicio = datetime.combine(data_atual, hora_aula)
            data_fim = data_inicio + timedelta(hours=1)

            google_id = None
            try:
                titulo_google = f"Turma {turma.tipo}: {turma.nome_turma}"
                
                # Chamamos a função atualizada passando o link_meet_da_turma
                # Ela retorna duas coisas: o ID do evento e o link
                google_id, link_retornado = criar_evento(
                    data_inicio, 
                    data_fim, 
                    titulo_google, 
                    meet_link_existente=link_meet_da_turma
                )
                
                # Se a turma não tinha link e o Google acabou de gerar o primeiro,
                # nós salvamos ele para usar nas próximas semanas deste loop
                if not link_meet_da_turma and link_retornado:
                    link_meet_da_turma = link_retornado
                    turma.meet_link = link_retornado
                    db.flush()
                
                print(f"✅ Sincronizado no Google: {data_inicio} | Meet: {link_meet_da_turma}")
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
                        # Se você quiser guardar o link na tabela 'aulas' também, adicione a coluna lá e chame: meet_link=link_meet_da_turma
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

        horarios_recebidos = dados.get('horarios', [])
        dias_extenso = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        
        # 1. Prepara as strings de exibição para a tabela Turma (evita o NULL)
        txt_dias = ", ".join([dias_extenso[int(h['dia'])] for h in horarios_recebidos])
        txt_horas = ", ".join([h['hora'] for h in horarios_recebidos])

        nova_turma = Turma(
            nome_turma=dados.get('nome_turma'),
            tipo=dados.get('tipo'),
            duracao_minutos=int(dados.get('duracao_minutos', 60)),
            capacidade_maxima=limite_max,
            dia_semana=txt_dias if txt_dias else None,
            horario=txt_horas if txt_horas else None,
            meet_link=dados.get('meet_link')
        )
        db.add(nova_turma)
        db.flush() # Gera o ID da turma para usar nos relacionamentos abaixo

        # 2. Salva os horários individuais na tabela horarios_aula
        for h in horarios_recebidos:
            novo_h = HorarioAula(
                turma_id=nova_turma.id,
                dia_da_semana=int(h['dia']),
                horario=datetime.strptime(h['hora'], "%H:%M").time()
            )
            db.add(novo_h)

        # 3. VINCULA OS ALUNOS (Importante: isso deve ser feito antes do gerar_aulas)
        aluno_ids = dados.get('aluno_ids', [])
        if aluno_ids:
            # Busca os alunos no banco
            alunos_no_db = db.query(Aluno).filter(Aluno.id.in_(aluno_ids)).all()
            for aluno in alunos_no_db:
                aluno.turma_id = nova_turma.id
                # Atualizamos o tipo do aluno para bater com o da turma (VIP, DUO ou TEAM)
                aluno.tipo = dados.get('tipo') 

        # 4. Salva tudo no banco de uma vez
        db.commit()

        # 5. Gera a agenda (agora que os alunos já estão na turma)
        try:
            gerar_aulas_da_semana(db) 
        except Exception as e_agenda:
            print(f"Erro ao gerar agenda inicial: {e_agenda}")

        return {"msg": f"Turma {nova_turma.nome_turma} criada com {len(horarios_recebidos)} horários!"}
        
    except Exception as e:
        db.rollback()
        print(f"Erro crítico ao criar turma: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{turma_id}")
def editar_turma(turma_id: int, dados: dict, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    try:
        # Atualiza apenas os campos permitidos vindos do front-end
        if "nome_turma" in dados:
            turma.nome_turma = dados.get("nome_turma")
        if "meet_link" in dados:
            turma.meet_link = dados.get("meet_link")
            
        db.commit()
        return {"status": "sucesso", "msg": f"Turma {turma.nome_turma} atualizada!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao salvar: {str(e)}")

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
            "meet_link": t.meet_link,
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

        # 1. Pegar IDs dos alunos para referências futuras
        alunos = db.query(models.Aluno).filter(models.Aluno.turma_id == turma_id).all()
        alunos_ids = [a.id for a in alunos]

        # 2. Coletar e remover eventos do Google Agenda (de ambas as tabelas)
        # Buscamos IDs tanto da tabela Aula quanto da HistoricoAula
        eventos_agenda = db.query(models.Aula.google_event_id).filter(models.Aula.turma_id == turma_id).all()
        eventos_hist = db.query(models.HistoricoAula.google_event_id).filter(models.HistoricoAula.aluno_id.in_(alunos_ids)).all() if alunos_ids else []
        
        # Unificamos os IDs únicos para não tentar deletar o mesmo evento duas vezes
        todos_g_ids = set([e[0] for e in eventos_agenda if e[0]] + [e[0] for e in eventos_hist if e[0]])

        for g_id in todos_g_ids:
            try:
                remover_evento_google(g_id)
            except Exception as e:
                print(f"Aviso Google (pode ignorar): {e}")

        # 3. LIMPEZA NO BANCO DE DADOS (A ordem aqui é CRÍTICA)
        
        # Passo A: Apagar as Aulas da Agenda (Tabela 'aulas') - RESOLVE O ERRO DA FK
        db.query(models.Aula).filter(models.Aula.turma_id == turma_id).delete(synchronize_session=False)

        # Passo B: Limpar Horários Semanais (Tabela 'horarios_aula')
        db.query(models.HorarioAula).filter(models.HorarioAula.turma_id == turma_id).delete(synchronize_session=False)

        if alunos_ids:
            # Passo C: Apagar histórico dos alunos
            db.query(models.HistoricoAula).filter(models.HistoricoAula.aluno_id.in_(alunos_ids)).delete(synchronize_session=False)
            
            # Passo D: Desvincular alunos da turma (setar NULL)
            db.query(models.Aluno).filter(models.Aluno.id.in_(alunos_ids)).update({"turma_id": None}, synchronize_session=False)

        # Passo E: Finalmente, apagar a Turma
        db.delete(turma)
        
        db.commit() 
        return {"msg": "Turma e todos os agendamentos deletados com sucesso!"}

    except Exception as e:
        db.rollback()
        print(f"ERRO AO DELETAR NO RENDER: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao deletar: {str(e)}")

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