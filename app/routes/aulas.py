import pytz
import os   
import traceback
from typing import Optional
from fastapi import APIRouter, Form, HTTPException, Depends, BackgroundTasks, Query as FastAPIQuery
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.auth import verificar_token
from app.services.whatsapp import enviar_whatsapp
from app.database import get_db # Removido SessionLocal daqui
from app.services.google_calendar import criar_evento, remover_evento_google
from app import models
from app.models import Aluno, Aula, GradeProfessor, HorarioAula, HistoricoAula, StatusAula 
from datetime import datetime, timedelta, time

TELEFONE_PROFESSOR = os.getenv("TELEFONE_PROFESSOR", "5522992011011")
router = APIRouter(prefix="/aulas", tags=["aulas"])

# ==============================
# MARCAR AULA
# ==============================
@router.post("/marcar")
def marcar_aula(aluno_id: int, data: str, hora: str, background_tasks: BackgroundTasks, eh_reposicao: bool = False, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        try:
            inicio = datetime.strptime(f"{data.strip()} {hora.strip()}", "%d-%m-%Y %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de data ou hora inválido.")

        fim = inicio + timedelta(hours=1)
        
        print(f"--- DEBUG MARCAR ---")
        print(f"Aluno: {aluno.nome} | Tipo: {aluno.tipo} | Turma ID: {aluno.turma_id}")
        
        lista_alunos = [aluno]
        if aluno.turma_id and aluno.tipo.value != "VIP":
            colegas = db.query(Aluno).filter(Aluno.turma_id == aluno.turma_id, Aluno.id != aluno.id).all()
            print(f"Encontrei {len(colegas)} colegas de turma.")
            lista_alunos.extend(colegas)
        
        print(f"Total de aulas a criar: {len(lista_alunos)}")
        print(f"--------------------")
        
        for pessoinha in lista_alunos:
            if eh_reposicao:
                creditos_reais = db.query(Aula).filter(
                    Aula.aluno_id == pessoinha.id,
                    Aula.status == "cancelado",
                    Aula.validade_reposicao >= datetime.now()
                ).count()

                if creditos_reais <= 0:
                    pessoinha.creditos_reposicao = 0 
                    db.commit()
                    raise HTTPException(
                        status_code=400, 
                        detail=f"O aluno {pessoinha.nome} não possui créditos válidos."
                    )
            else:
                uma_semana_atras = inicio - timedelta(days=7)
                aulas_na_semana = db.query(Aula).filter(
                    Aula.aluno_id == pessoinha.id,
                    Aula.data_inicio >= uma_semana_atras,
                    Aula.status == "marcada"
                ).count()
                
                limite = pessoinha.limite_aulas_semana or 1
                if aulas_na_semana >= limite:
                    raise HTTPException(status_code=400, detail=f"Limite de {pessoinha.nome} atingido.")

        conflito = db.query(Aula).filter(
            Aula.data_inicio < fim,
            Aula.data_fim > inicio,
            Aula.status.in_(["marcada", "presente"]) 
        ).first()

        if conflito:
            raise HTTPException(status_code=400, detail="Este horário já está ocupado.")
        
        g_id = None  
        meet_link = None
        titulo_aula = f"Aula: {aluno.nome}" if len(lista_alunos) == 1 else f"Aula Turma: {aluno.turma.nome if aluno.turma else 'Coletiva'}"
        try:
            g_id, meet_link = criar_evento(inicio, fim, titulo_aula)
        except Exception as ge:
            print(f"DEBUG: Falha Google Calendar: {ge}")

        novas_aulas = []
        for p in lista_alunos:
            data_validade = None
            if eh_reposicao:
                # ... sua lógica de reposição ...
                pass

            nova = Aula(
                aluno_id=p.id,
                turma_id=p.turma_id,
                data_inicio=inicio,
                data_fim=fim,
                # ALTERAÇÃO AQUI: Use o Enum em vez de string se o seu model pedir StatusAula
                status=StatusAula.marcada, 
                google_event_id=g_id,
                eh_reposicao=eh_reposicao,
                validade_reposicao=data_validade,
                lembrete_enviado=False
            )
            novas_aulas.append(nova)

            # --- ADICIONE ISTO PARA APARECER NO HISTÓRICO/LISTA PROFESSOR ---
            novo_hist = HistoricoAula(
                aluno_id=p.id,
                data_aula=inicio,
                status_presenca=False,
                chamada_realizada=False,
                google_event_id=g_id,
                observacao="Aula de Turma Agendada" if p.turma_id else "Aula VIP Agendada"
            )
            db.add(novo_hist)
            # -------------------------------------------------------------

        db.add_all(novas_aulas)
        db.commit()
        
        for aula_criada in novas_aulas:
            msg_confirmacao = (
                f"Agendado com sucesso, {aula_criada.aluno.nome}! ✅\n\n"
                f"Sua aula será dia {aula_criada.data_inicio.strftime('%d/%m')} "
                f"às {aula_criada.data_inicio.strftime('%H:%M')}.\n"
                f"{'★ Aula de Reposição' if eh_reposicao else ''}"
            )
            background_tasks.add_task(enviar_whatsapp, aula_criada.aluno.telefone, msg_confirmacao)

        return {"status": "sucesso", "event_id": g_id, "google_sync": True if g_id else False}

    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro técnico interno.")

@router.post("/avulsa")
async def criar_aula_avulsa(dados: dict, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        aluno_id = int(dados['aluno_id'])
        aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        inicio = datetime.fromisoformat(dados['data_inicio'])
        fim = inicio + timedelta(hours=1)

        google_event_id = None
        meet_link_avulso = None
        titulo_aula = f"Aula VIP: {aluno.nome} {aluno.sobrenome or ''}"
        try:
            google_event_id, meet_link_avulso = criar_evento(inicio, fim, titulo_aula)
        except Exception as ge:
            print(f"DEBUG: Falha Google Calendar: {ge}")

        nova_aula = Aula(aluno_id=aluno_id, data_inicio=inicio, data_fim=fim, status=StatusAula.marcada, google_event_id=google_event_id)
        db.add(nova_aula)
        db.flush() 

        novo_historico = HistoricoAula(
            aluno_id=aluno_id,
            data_aula=inicio,
            status_presenca=False,
            observacao="Aula Avulsa Agendada",
            google_event_id=google_event_id
        )
        db.add(novo_historico)
        db.commit()
        return {"msg": "Aula agendada!", "id_historico": novo_historico.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# ==============================
# LISTAR AULAS
# ==============================
@router.get("/")
def listar_aulas(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aulas = db.query(Aula).order_by(Aula.data_inicio).all()
    return [{"id": a.id, "aluno_id": a.aluno_id, "data_inicio": a.data_inicio, "data_fim": a.data_fim, "status": a.status, "google_event_id": a.google_event_id} for a in aulas]

# ==============================
# HORÁRIOS LIVRES
# ==============================
@router.get("/horarios-livres")
def horarios_livres(data: str, token: str = None, db: Session = Depends(get_db)):
    try:
        data_base = datetime.strptime(data, "%d-%m-%Y")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido")

    if token:
        aluno = db.query(Aluno).filter(Aluno.token_acesso == token).first()
        if aluno and aluno.turma_id and aluno.tipo.value != "VIP":
            aula_turma = db.query(Aula).join(Aluno).filter(
                Aluno.turma_id == aluno.turma_id,
                func.date(Aula.data_inicio) == data_base.date(),
                Aula.status == "marcada"
            ).first()
            if aula_turma:
                return {"aula_marcada_pela_turma": True, "horario_turma": aula_turma.data_inicio.strftime("%H:%M"), "horarios_livres": []}

    dia_semana_atual = data_base.weekday()
    turnos_professor = db.query(GradeProfessor).filter(GradeProfessor.dia_semana == dia_semana_atual, GradeProfessor.ativo == True).all()

    if not turnos_professor:
        return {"data": data, "msg": "O professor não atende neste dia.", "horarios_livres": []}

    horarios_possiveis = []
    for turno in turnos_professor:
        h_inicio = datetime.strptime(turno.hora_inicio, "%H:%M").time()
        h_fim = datetime.strptime(turno.hora_fim, "%H:%M").time()
        atual = datetime.combine(data_base, h_inicio)
        fim_turno = datetime.combine(data_base, h_fim)
        while atual < fim_turno:
            horarios_possiveis.append(atual)
            atual += timedelta(hours=1)

    inicio_dia = datetime.combine(data_base, time(0, 0))
    fim_dia = datetime.combine(data_base, time(23, 59))
    aulas_marcadas = db.query(Aula).filter(Aula.data_inicio >= inicio_dia, Aula.data_inicio <= fim_dia, Aula.status == "marcada").all()
    horarios_ocupados = [a.data_inicio for a in aulas_marcadas]

    livres = [h.strftime("%H:%M") for h in horarios_possiveis if h not in horarios_ocupados and h > datetime.now()]
    return {"data": data, "horarios_livres": sorted(list(set(livres)))}

# ==============================
# CANCELAR AULA (PORTAL)
# ==============================
@router.post("/{aula_id}/cancelar/{token}")
def cancelar_aula(aula_id: int, token: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_br).replace(tzinfo=None)
    aula = db.query(Aula).join(Aluno).filter(Aula.id == aula_id, Aluno.token_acesso == token).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada.")

    aluno = aula.aluno
    if aluno.tipo.value != "VIP":
        raise HTTPException(status_code=403, detail="Apenas plano VIP cancela pelo portal.")

    gera_reposicao = (aula.data_inicio - agora) >= timedelta(hours=3)
    novo_status = StatusAula.cancelado if gera_reposicao else StatusAula.ausente

    if aula.google_event_id:
        try:
            remover_evento_google(aula.google_event_id)
        except Exception as e:
            print(f"Erro Google: {e}")

    aula.status = novo_status
    aula.google_event_id = None 
    validade_formatada = None

    if gera_reposicao:
        aluno.creditos_reposicao += 1
        data_validade = agora + timedelta(days=30)
        aula.validade_reposicao = data_validade
        validade_formatada = data_validade.strftime('%d/%m/%Y')

    # Sincronização com a tabela HistoricoAula para atualizar o cronograma do professor
    historicos = db.query(HistoricoAula).filter(
        HistoricoAula.aluno_id == aluno.id,
        func.date(HistoricoAula.data_aula) == func.date(aula.data_inicio)
    ).all()

    for hist in historicos:
        hist.chamada_realizada = True
        hist.status_presenca = False
        hist.observacao = f"Aula Cancelada pelo Aluno ({'Com reposição' if gera_reposicao else 'Sem reposição'})"

    db.commit()

    link_portal = f"https://smart-booking-saas.onrender.com/portal/{aluno.token_acesso}"

    msg = f"Olá {aluno.nome}! ⚠️\nSua aula de *{aula.data_inicio.strftime('%d/%m às %H:%M')}* foi cancelada."
    
    if gera_reposicao:
        msg += (
            f"\n✅ *Reposição gerada.*\n"
            f"📅 Válida até: *{validade_formatada}*.\n\n"
            f"Você já pode reagendar sua aula através do seu portal:\n"
            f"{link_portal}"
        )
    else:
        msg += "\n❌ Sem direito a reposição (cancelamento tardio)."
    
    background_tasks.add_task(enviar_whatsapp, aluno.telefone, msg)

    # Notificação para o professor
    msg_professor = (
        f"🚨 *Aula Cancelada pelo Aluno* 🚨\n\n"
        f"O aluno *{aluno.nome} {aluno.sobrenome or ''}* cancelou a aula de "
        f"*{aula.data_inicio.strftime('%d/%m às %H:%M')}* pelo portal.\n\n"
        f"{'✅ Crédito de reposição gerado.' if gera_reposicao else '❌ Sem direito a reposição (cancelamento tardio).'}"
    )
    background_tasks.add_task(enviar_whatsapp, TELEFONE_PROFESSOR, msg_professor)

    return {"status": "sucesso", "creditos": aluno.creditos_reposicao}

# ==============================
# GRADE E HISTÓRICO (ADMIN)
# ==============================
@router.post("/configurar-grade")
def configurar_grade(dia: int, inicio: str, fim: str, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    nova_grade = GradeProfessor(dia_semana=dia, hora_inicio=inicio, hora_fim=fim, ativo=True)
    db.add(nova_grade)
    db.commit()
    return {"msg": "Grade configurada"}

@router.get("/grade")
def listar_grade(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    return db.query(GradeProfessor).all()

@router.delete("/grade/{id}")
def deletar_grade(id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    turno = db.query(GradeProfessor).filter(GradeProfessor.id == id).first()
    if not turno: raise HTTPException(status_code=404)
    db.delete(turno)
    db.commit()
    return {"msg": "Removido"}

@router.get("/lista-professor")
def listar_aulas_professor(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    fuso_br = pytz.timezone('America/Sao_Paulo')
    # Pegamos o agora no Brasil para filtrar corretamente
    agora_br = datetime.now(fuso_br).replace(tzinfo=None)
    
    # Filtramos aulas que terminam a partir de 3 horas atrás (margem de segurança)
    resultados = db.query(Aula, Aluno, HistoricoAula.id).\
        join(Aluno, Aula.aluno_id == Aluno.id).\
        outerjoin(HistoricoAula, (HistoricoAula.aluno_id == Aula.aluno_id) & (func.date(HistoricoAula.data_aula) == func.date(Aula.data_inicio))).\
        filter(Aula.data_fim >= agora_br - timedelta(hours=3)).\
        filter(Aula.status == StatusAula.marcada).\
        order_by(Aula.data_inicio.asc()).all()
    
    agrupado = {}
    for aula, aluno, historico_id in resultados:
        id_para_presenca = historico_id if historico_id else aula.id
        # Chave de agrupamento: Data + Turma (ou ID do aluno se for VIP)
        chave = f"{aula.data_inicio.isoformat()}_{aula.turma_id or f'vip_{aluno.id}'}"
        
        if chave not in agrupado:
            agrupado[chave] = {
                "data_inicio": aula.data_inicio.isoformat(),
                "turma_id": aula.turma_id,
                "status": aula.status.name if hasattr(aula.status, 'name') else str(aula.status),
                "nome_exibicao": aula.turma.nome_turma if aula.turma_id and aula.turma else f"{aluno.nome} {aluno.sobrenome or ''}",
                "tipo": "TURMA" if aula.turma_id else "VIP",
                "is_turma": bool(aula.turma_id),
                "alunos": []
            }
        agrupado[chave]["alunos"].append({
            "aula_id": id_para_presenca, 
            "aluno_id": aluno.id, 
            "nome": f"{aluno.nome} {aluno.sobrenome or ''}"
        })
    return list(agrupado.values())

@router.patch("/{aula_id}/presenca")
def marcar_presenca_agenda(
    aula_id: int, 
    status: str = FastAPIQuery(...), 
    desempenho: str = FastAPIQuery(...), 
    observacao: str = FastAPIQuery(""), 
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    # 1. Busca a aula na tabela de Agenda (aulas)
    # Importante: No seu painel, o ID enviado pode ser o da Aula ou do Histórico.
    # Vamos tratar o caso da Aula primeiro.
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    
    if not aula:
        # Se não achou na agenda, talvez o front já enviou o ID do histórico
        return marcar_presenca(aula_id, status, desempenho, observacao, db, usuario)

    # 2. Define o booleano de presença
    is_presente = (status.strip().lower() == 'presente')

    # 3. Atualiza o status na tabela de Agenda (Enum StatusAula)
    aula.status = StatusAula.presente if is_presente else StatusAula.ausente

    # 4. SINCRONIZAÇÃO: Busca ou Cria o registro no Histórico
    # Procuramos um histórico para este aluno na mesma data desta aula
    aula_hist = db.query(HistoricoAula).filter(
        HistoricoAula.aluno_id == aula.aluno_id,
        func.date(HistoricoAula.data_aula) == func.date(aula.data_inicio)
    ).first()

    if not aula_hist:
        # Se não existe histórico (aula avulsa antiga), criamos um profissional agora
        aula_hist = HistoricoAula(
            aluno_id=aula.aluno_id,
            data_aula=aula.data_inicio,
            google_event_id=aula.google_event_id
        )
        db.add(aula_hist)
    
    # 5. Preenche os dados pedagógicos e fecha a chamada
    aula_hist.status_presenca = is_presente
    aula_hist.desempenho = desempenho
    aula_hist.observacao = observacao
    aula_hist.chamada_realizada = True  # <--- Isso faz ela sumir da lista de pendentes

    db.commit()
    return {"msg": "Presença registrada na agenda e histórico atualizado"}

# Note que mudei o caminho da rota para bater com o que o seu terminal mostrou (404)
@router.patch("/admin/presenca-retroativa/{aula_id}")
def marcar_presenca(
    aula_id: int, 
    status: str = FastAPIQuery(...), 
    desempenho: str = FastAPIQuery(...), 
    observacao: str = FastAPIQuery(""), 
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    aula_hist = db.query(HistoricoAula).filter(HistoricoAula.id == aula_id).first()
    if not aula_hist: 
        raise HTTPException(status_code=404)

    # LÓGICA BLINDADA: 
    # Somente se a string for exatamente 'presente' (ignora maiúsculas/minúsculas)
    is_presente = (status.strip().lower() == 'presente')
    
    aula_hist.status_presenca = is_presente
    aula_hist.desempenho = desempenho
    aula_hist.observacao = observacao
    aula_hist.chamada_realizada = True  # <--- CRUCIAL para sumir da lista

    # Sincroniza com a tabela 'aulas' (Agenda)
    aula_agenda = db.query(Aula).filter(
        Aula.aluno_id == aula_hist.aluno_id,
        func.date(Aula.data_inicio) == func.date(aula_hist.data_aula)
    ).first()

    if aula_agenda:
        # Usa o Enum StatusAula que definimos no models.py
        aula_agenda.status = StatusAula.presente if is_presente else StatusAula.ausente

    db.commit()
    return {"msg": "Registro atualizado", "status_salvo": "Presente" if is_presente else "Ausente"}
    
@router.get("/admin/historico-geral")
def listar_historico_geral(
    finalizadas: bool = False, 
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    agora = datetime.now()
    
    query = db.query(HistoricoAula).filter(HistoricoAula.data_aula <= agora)
    
    if not finalizadas:
        query = query.filter(HistoricoAula.chamada_realizada == False)
    
    registros = query.order_by(HistoricoAula.data_aula.desc()).all()
    
    registros = query.order_by(HistoricoAula.data_aula.desc()).all()
    
    agrupado = {}
    for reg in registros:
        aluno = db.query(Aluno).filter(Aluno.id == reg.aluno_id).first()
        if not aluno: 
            continue
            
        data_formatada = reg.data_aula.date() if hasattr(reg.data_aula, 'date') else reg.data_aula
        chave = f"{data_formatada}_{aluno.turma_id if aluno.turma_id else f'vip_{aluno.id}'}"
        
        if chave not in agrupado:
            agrupado[chave] = {
                "data": reg.data_aula.isoformat() if hasattr(reg.data_aula, 'isoformat') else str(reg.data_aula),
                "nome_exibicao": aluno.turma.nome_turma if aluno.turma_id else f"{aluno.nome} {aluno.sobrenome or ''}",
                "is_turma": bool(aluno.turma_id),
                "alunos": []
            }
        
        agrupado[chave]["alunos"].append({
            "historico_id": reg.id, 
            "nome": f"{aluno.nome} {aluno.sobrenome or ''}", 
            "status_presenca": reg.status_presenca, 
            "desempenho": reg.desempenho, 
            "observacao": reg.observacao
        })
    
    return list(agrupado.values())

@router.get("/admin/estatisticas-mes")
def obter_estatisticas(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    hoje = datetime.now()
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0)
    filtro_tempo = (HistoricoAula.data_aula >= inicio_mes) & (HistoricoAula.data_aula <= hoje)
    total = db.query(HistoricoAula).filter(filtro_tempo).count()
    presencas = db.query(HistoricoAula).filter(filtro_tempo, HistoricoAula.status_presenca == True).count()
    faltosos = db.query(Aluno.nome, func.count(HistoricoAula.id)).join(HistoricoAula).filter(filtro_tempo, HistoricoAula.status_presenca == False).group_by(Aluno.id).order_by(func.count(HistoricoAula.id).desc()).limit(3).all()
    taxa = (presencas / total * 100) if total > 0 else 0
    return {"taxa_presenca": round(taxa, 1), "total_aulas": total, "alunos_faltosos": [{"nome": f[0], "faltas": f[1]} for f in faltosos]}

@router.delete("/cancelar-grupo")
def cancelar_aula_grupo(data_inicio: str = FastAPIQuery(...), turma_id: Optional[int] = FastAPIQuery(None), aluno_id: Optional[int] = FastAPIQuery(None), db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        limpo = data_inicio.replace('Z', '+00:00').split('.')[0]
        dt_inicio = datetime.fromisoformat(limpo)
    except: raise HTTPException(status_code=400, detail="Data inválida")
    query = db.query(Aula).filter(Aula.data_inicio == dt_inicio)
    if turma_id: query = query.filter(Aula.turma_id == turma_id)
    elif aluno_id: query = query.filter(Aula.aluno_id == aluno_id)
    aulas = query.all()
    if not aulas: return {"msg": "Nada encontrado", "count": 0}
    google_id = aulas[0].google_event_id
    if google_id:
        try: remover_evento_google(google_id)
        except: pass
    for a in aulas: db.delete(a)
    db.commit()
    return {"msg": "Removido", "count": len(aulas)}

@router.delete("/{aula_id}")
def deletar_aula(aula_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if not aula: raise HTTPException(status_code=404)
    if aula.google_event_id:
        try: remover_evento_google(aula.google_event_id)
        except: pass
    db.delete(aula)
    db.commit()
    return {"msg": "Excluído"}

@router.get("/historico/{aluno_id}")
def obter_historico_aluno(aluno_id: int, db: Session = Depends(get_db)):
    return db.query(Aula).filter(Aula.aluno_id == aluno_id, Aula.status.in_(['presente', 'ausente', 'Presente', 'Ausente'])).order_by(Aula.data_inicio.desc()).all()

@router.get("/relatorio-aluno/{aluno_id}")
def obter_relatorio_pedagogico(aluno_id: int, db: Session = Depends(get_db)):
    historico = db.query(HistoricoAula).filter(HistoricoAula.aluno_id == aluno_id).order_by(HistoricoAula.data_aula.desc()).all()
    return [{"data": h.data_aula.strftime("%d/%m/%Y") if hasattr(h.data_aula, 'strftime') else str(h.data_aula), "presenca": "✅" if h.status_presenca is True else "❌", "desempenho": h.desempenho or "Sem avaliação", "observacao": h.observacao or "-"} for h in historico]