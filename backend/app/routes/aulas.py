import traceback
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query as FastAPIQuery
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from app.auth import verificar_token
from app.services.whatsapp import enviar_whatsapp
from app.database import get_db # Removido SessionLocal daqui
from app.services.google_calendar import criar_evento, remover_evento_google
from app.models import Aluno, Aula, GradeProfessor, HistoricoAula, Professor, StatusAula
from datetime import datetime, timedelta
from app.core.config import BASE_URL, TELEFONE_PROFESSOR, agora_br
from app.services.agendamento import duracao_aula_minutos
from app.services.creditos import consumir_credito, query_creditos_validos, sincronizar_contador_creditos
from app.services.disponibilidade import contar_reservas_simultaneas, resolver_grade_disponivel

router = APIRouter(prefix="/aulas", tags=["aulas"])


def historicos_vinculados_a_aula(db: Session, aula: Aula):
    vinculados = db.query(HistoricoAula).filter(HistoricoAula.aula_id == aula.id).all()
    if vinculados:
        return vinculados

    legado = db.query(HistoricoAula).filter(
        HistoricoAula.aula_id.is_(None),
        HistoricoAula.aluno_id == aula.aluno_id,
        HistoricoAula.data_aula == aula.data_inicio,
    ).order_by(HistoricoAula.id.asc()).first()
    if legado:
        legado.aula_id = aula.id
        return [legado]
    return []

# ==============================
# MARCAR AULA
# ==============================
@router.post("/marcar")
def marcar_aula(
    aluno_id: int, 
    data: str, 
    hora: str, 
    background_tasks: BackgroundTasks, 
    eh_reposicao: bool = False, 
    grade_id: Optional[int] = FastAPIQuery(None),
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    try:
        aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        try:
            inicio = datetime.strptime(f"{data.strip()} {hora.strip()}", "%d-%m-%Y %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de data ou hora inválido.")

        fim = inicio + timedelta(minutes=duracao_aula_minutos(db, aluno))
        
        professor_id = None
        cap_max = 1
        if grade_id:
            turno_ref = resolver_grade_disponivel(
                db, inicio, fim, grade_id_preferida=grade_id, bloquear=True
            )
            if not turno_ref or turno_ref.id != grade_id:
                raise HTTPException(
                    status_code=409,
                    detail="O turno selecionado está inativo, incompatível ou sem vagas.",
                )
            professor_id = turno_ref.professor_id
            cap_max = max(int(turno_ref.capacidade or 1), 1)
        elif aluno.turma_id and aluno.turma and aluno.turma.professor_id:
            professor_id = aluno.turma.professor_id

        lista_alunos = [aluno]
        if aluno.turma_id and aluno.tipo.value != "VIP":
            colegas = db.query(Aluno).filter(Aluno.turma_id == aluno.turma_id, Aluno.id != aluno.id).all()
            lista_alunos.extend(colegas)
        
        for pessoinha in lista_alunos:
            if eh_reposicao:
                creditos_reais = query_creditos_validos(db, pessoinha.id).count()

                if creditos_reais <= 0:
                    pessoinha.creditos_reposicao = 0 
                    raise HTTPException(
                        status_code=400, 
                        detail=f"O aluno {pessoinha.nome} não possui créditos válidos."
                    )
            else:
                inicio_semana = (inicio - timedelta(days=inicio.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                aulas_na_semana = db.query(Aula).filter(
                    Aula.aluno_id == pessoinha.id,
                    Aula.data_inicio >= inicio_semana,
                    Aula.status == StatusAula.marcada
                ).count()
                
                limite = pessoinha.limite_aulas_semana or 1
                if aulas_na_semana >= limite:
                    raise HTTPException(status_code=400, detail=f"Limite de {pessoinha.nome} atingido.")

        ocupadas = contar_reservas_simultaneas(db, inicio, fim, professor_id)
        if ocupadas >= cap_max:
            raise HTTPException(status_code=400, detail="Este horário já está ocupado para o professor selecionado.")
        
        g_id = None  
        meet_link = None
        titulo_aula = f"Aula: {aluno.nome}" if len(lista_alunos) == 1 else f"Aula Turma: {aluno.turma.nome_turma if aluno.turma else 'Coletiva'}"
        try:
            g_id, meet_link = criar_evento(inicio, fim, titulo_aula)
        except Exception as ge:
            print(f"DEBUG: Falha Google Calendar: {ge}")

        novas_aulas = []
        for p in lista_alunos:
            data_validade = None
            if eh_reposicao:
                consumir_credito(db, p)

            nova = Aula(
                aluno_id=p.id,
                turma_id=p.turma_id,
                professor_id=professor_id,
                data_inicio=inicio,
                data_fim=fim,
                status=StatusAula.marcada, 
                google_event_id=g_id,
                eh_reposicao=eh_reposicao,
                validade_reposicao=data_validade,
                lembrete_enviado=False
            )
            db.add(nova)
            db.flush()
            novas_aulas.append(nova)

            novo_hist = HistoricoAula(
                aula_id=nova.id,
                aluno_id=p.id,
                data_aula=inicio,
                status_presenca=False,
                chamada_realizada=False,
                google_event_id=g_id,
                observacao="Aula de Turma Agendada" if p.turma_id else "Aula VIP Agendada"
            )
            db.add(novo_hist)

        db.commit()

        prof_nome = None
        if professor_id:
            from app.models import Professor
            prof_obj = db.query(Professor).filter(Professor.id == professor_id).first()
            if prof_obj:
                prof_nome = prof_obj.nome
        
        for aula_criada in novas_aulas:
            msg_confirmacao = (
                f"Agendado com sucesso, {aula_criada.aluno.nome}! ✅\n\n"
                f"Sua aula será dia {aula_criada.data_inicio.strftime('%d/%m')} "
                f"às {aula_criada.data_inicio.strftime('%H:%M')}.\n"
                f"{'★ Aula de Reposição' if eh_reposicao else ''}"
            )
            if prof_nome:
                msg_confirmacao += f"\n👨‍🏫 Professor(a): {prof_nome}"

            background_tasks.add_task(enviar_whatsapp, aula_criada.aluno.telefone, msg_confirmacao)

        return {"status": "sucesso", "event_id": g_id, "google_sync": True if g_id else False}

    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        db.rollback()
        print(f"ERRO EM MARCAR AULA: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.post("/avulsa")
async def criar_aula_avulsa(dados: dict, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    try:
        aluno_id = int(dados['aluno_id'])
        aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        inicio = datetime.fromisoformat(dados['data_inicio'])
        fim = inicio + timedelta(minutes=duracao_aula_minutos(db, aluno))
        grade_id = int(dados["grade_id"]) if dados.get("grade_id") else None
        professor_id = None
        if grade_id:
            turno = resolver_grade_disponivel(db, inicio, fim, grade_id_preferida=grade_id, bloquear=True)
            if not turno or turno.id != grade_id:
                raise HTTPException(status_code=409, detail="Turno sem vagas para a duração escolhida.")
            professor_id = turno.professor_id
        elif aluno.turma and aluno.turma.professor_id:
            professor_id = aluno.turma.professor_id
        if not grade_id and contar_reservas_simultaneas(db, inicio, fim, professor_id) >= 1:
            raise HTTPException(status_code=409, detail="Já existe uma aula neste horário.")


        google_event_id = None
        meet_link_avulso = None
        titulo_aula = f"Aula VIP: {aluno.nome} {aluno.sobrenome or ''}"
        try:
            google_event_id, meet_link_avulso = criar_evento(inicio, fim, titulo_aula)
        except Exception as ge:
            print(f"DEBUG: Falha Google Calendar: {ge}")

        nova_aula = Aula(
            aluno_id=aluno_id,
            turma_id=aluno.turma_id,
            professor_id=professor_id,
            data_inicio=inicio,
            data_fim=fim,
            status=StatusAula.marcada,
            google_event_id=google_event_id,
        )
        db.add(nova_aula)
        db.flush() 

        novo_historico = HistoricoAula(
            aula_id=nova_aula.id,
            aluno_id=aluno_id,
            data_aula=inicio,
            status_presenca=False,
            chamada_realizada=False,
            observacao="Aula Avulsa Agendada",
            google_event_id=google_event_id
        )
        db.add(novo_historico)
        db.commit()
        return {"msg": "Aula agendada!", "id_historico": novo_historico.id}
    except HTTPException:
        db.rollback()
        raise
    except (KeyError, TypeError, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")

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

    aluno = None
    if token:
        aluno = db.query(Aluno).filter(Aluno.token_acesso == token).first()
        if not aluno:
            raise HTTPException(status_code=404, detail="Token de aluno inválido.")
        if aluno and aluno.turma_id and aluno.tipo.value != "VIP":
            aula_turma = db.query(Aula).join(Aluno).filter(
                Aluno.turma_id == aluno.turma_id,
                func.date(Aula.data_inicio) == data_base.date(),
                Aula.status == StatusAula.marcada
            ).first()
            if aula_turma:
                return {"aula_marcada_pela_turma": True, "horario_turma": aula_turma.data_inicio.strftime("%H:%M"), "horarios_livres": []}

    dia_semana_atual = data_base.weekday()
    turnos_professor = db.query(GradeProfessor).outerjoin(
        Professor, GradeProfessor.professor_id == Professor.id
    ).filter(
        GradeProfessor.dia_semana == dia_semana_atual, 
        GradeProfessor.ativo.is_(True),
        or_(GradeProfessor.professor_id.is_(None), Professor.ativo.is_(True)),
    ).all()

    if not turnos_professor:
        return {"data": data, "msg": "Sem horários configurados para este dia.", "horarios_livres": []}

    agora = agora_br()
    duracao_minutos = duracao_aula_minutos(db, aluno) if aluno else 60
    slots_encontrados = []

    for turno in turnos_professor:
        h_inicio = datetime.strptime(turno.hora_inicio, "%H:%M").time()
        h_fim = datetime.strptime(turno.hora_fim, "%H:%M").time()
        atual = datetime.combine(data_base, h_inicio)
        fim_turno = datetime.combine(data_base, h_fim)

        while atual < fim_turno:
            inicio_slot = atual
            fim_slot = atual + timedelta(minutes=duracao_minutos)
            atual += timedelta(hours=1)

            if inicio_slot <= agora or fim_slot > fim_turno:
                continue

            aulas_no_slot = contar_reservas_simultaneas(db, inicio_slot, fim_slot, turno.professor_id)
            capacidade_turno = turno.capacidade if (turno.capacidade and turno.capacidade > 0) else 1
            vagas_disponiveis = capacidade_turno - aulas_no_slot

            if vagas_disponiveis > 0:
                slots_encontrados.append({
                    "hora": inicio_slot.strftime("%H:%M"),
                    "grade_id": turno.id,
                    "vagas": vagas_disponiveis
                })

    slots_por_hora = {}
    for s in slots_encontrados:
        h = s["hora"]
        if h not in slots_por_hora:
            slots_por_hora[h] = {"hora": h, "grade_id": s["grade_id"], "vagas": s["vagas"]}
        else:
            slots_por_hora[h]["vagas"] += s["vagas"]

    horarios_livres_res = sorted(list(slots_por_hora.values()), key=lambda x: x["hora"])
    return {"data": data, "horarios_livres": horarios_livres_res}

# ==============================
# CANCELAR AULA (PORTAL)
# ==============================
@router.post("/{aula_id}/cancelar/{token}")
def cancelar_aula(aula_id: int, token: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    agora = agora_br()
    aula = db.query(Aula).join(Aluno).filter(Aula.id == aula_id, Aluno.token_acesso == token).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada.")

    aluno = aula.aluno
    if aluno.tipo.value != "VIP":
        raise HTTPException(status_code=403, detail="Apenas plano VIP cancela pelo portal.")
    if aula.status != StatusAula.marcada:
        raise HTTPException(status_code=409, detail="Esta aula já foi finalizada ou cancelada.")

    gera_reposicao = (aula.data_inicio - agora) >= timedelta(hours=3)
    novo_status = StatusAula.cancelado if gera_reposicao else StatusAula.ausente

    if aula.google_event_id:
        try:
            remover_evento_google(aula.google_event_id)
        except Exception as e:
            print(f"Erro Google: {e}")

    aula.status = novo_status
    aula.cancelada_em = agora
    aula.credito_consumido_em = None
    aula.google_event_id = None 
    validade_formatada = None

    if gera_reposicao:
        data_validade = agora + timedelta(days=30)
        aula.validade_reposicao = data_validade
        validade_formatada = data_validade.strftime('%d/%m/%Y')

    db.flush()
    sincronizar_contador_creditos(db, aluno, agora)
    historicos = historicos_vinculados_a_aula(db, aula)

    for hist in historicos:
        hist.chamada_realizada = True
        hist.status_presenca = False
        hist.observacao = f"Aula Cancelada pelo Aluno ({'Com reposição' if gera_reposicao else 'Sem reposição'})"

    db.commit()

    link_portal = f"{BASE_URL}/portal/{aluno.token_acesso}"

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
    if TELEFONE_PROFESSOR:
        background_tasks.add_task(enviar_whatsapp, TELEFONE_PROFESSOR, msg_professor)

    return {"status": "sucesso", "creditos": aluno.creditos_reposicao}

# ==============================
# GRADE E HISTÓRICO (ADMIN)
# ==============================
@router.post("/configurar-grade")
def configurar_grade(
    dia: int, 
    inicio: str, 
    fim: str, 
    professor_id: Optional[int] = FastAPIQuery(None), 
    capacidade: int = FastAPIQuery(1), 
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    if not 0 <= dia <= 6:
        raise HTTPException(status_code=400, detail="Dia da semana inválido.")
    if not 1 <= capacidade <= 10:
        raise HTTPException(status_code=400, detail="A capacidade deve ficar entre 1 e 10.")
    try:
        inicio_dt = datetime.strptime(inicio, "%H:%M")
        fim_dt = datetime.strptime(fim, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Horário inválido.")
    if inicio_dt >= fim_dt:
        raise HTTPException(status_code=400, detail="O fim do turno deve ser posterior ao início.")
    if professor_id and not db.query(Professor).filter(Professor.id == professor_id, Professor.ativo.is_(True)).first():
        raise HTTPException(status_code=400, detail="Professor inexistente ou inativo.")

    nova_grade = GradeProfessor(
        dia_semana=dia, 
        hora_inicio=inicio, 
        hora_fim=fim, 
        ativo=True,
        professor_id=professor_id,
        capacidade=capacidade
    )
    db.add(nova_grade)
    db.commit()
    return {"msg": "Grade configurada", "id": nova_grade.id}

@router.get("/grade")
def listar_grade(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    grades = db.query(GradeProfessor).all()
    resultado = []
    for g in grades:
        prof_nome = g.professor.nome if g.professor else None
        resultado.append({
            "id": g.id,
            "dia_semana": g.dia_semana,
            "hora_inicio": g.hora_inicio,
            "hora_fim": g.hora_fim,
            "ativo": g.ativo,
            "professor_id": g.professor_id,
            "nome_professor": prof_nome,
            "capacidade": g.capacidade or 1
        })
    return resultado

@router.delete("/grade/{id}")
def deletar_grade(id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    turno = db.query(GradeProfessor).filter(GradeProfessor.id == id).first()
    if not turno: raise HTTPException(status_code=404)
    db.delete(turno)
    db.commit()
    return {"msg": "Removido"}

@router.get("/lista-professor")
def listar_aulas_professor(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    agora = agora_br()
    
    # Filtramos aulas que terminam a partir de 3 horas atrás (margem de segurança)
    resultados = db.query(Aula, Aluno, HistoricoAula.id).\
        join(Aluno, Aula.aluno_id == Aluno.id).\
        outerjoin(HistoricoAula, HistoricoAula.aula_id == Aula.id).\
        filter(Aula.data_fim >= agora - timedelta(hours=3)).\
        filter(Aula.status == StatusAula.marcada).\
        order_by(Aula.data_inicio.asc()).all()
    
    agrupado = {}
    for aula, aluno, historico_id in resultados:
        id_para_presenca = aula.id
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
                "professor_id": aula.professor_id,
                "professor_nome": aula.professor.nome if aula.professor else None,
                "professor_cor": aula.professor.cor if aula.professor else None,
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

    historicos = historicos_vinculados_a_aula(db, aula)
    aula_hist = historicos[0] if historicos else None
    if not aula_hist:
        aula_hist = HistoricoAula(
            aula_id=aula.id,
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

    if aula_hist.aula_id:
        aula_agenda = db.query(Aula).filter(Aula.id == aula_hist.aula_id).first()
    else:
        aula_agenda = db.query(Aula).filter(
            Aula.aluno_id == aula_hist.aluno_id,
            Aula.data_inicio == aula_hist.data_aula,
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
    usuario: str = Depends(verificar_token),
):
    agora = agora_br()
    query = (
        db.query(HistoricoAula, Aluno, Aula)
        .join(Aluno, HistoricoAula.aluno_id == Aluno.id)
        .outerjoin(Aula, HistoricoAula.aula_id == Aula.id)
        .filter(
            HistoricoAula.data_aula <= agora,
            HistoricoAula.chamada_realizada.is_(finalizadas),
            or_(
                Aula.status != StatusAula.cancelado,
                and_(
                    Aula.id.is_(None),
                    ~func.lower(func.coalesce(HistoricoAula.observacao, "")).like("%cancelad%"),
                ),
            ),
        )
        .order_by(HistoricoAula.data_aula.desc(), HistoricoAula.id.asc())
    )

    agrupado = {}
    for registro, aluno, aula in query.all():
        turma = aula.turma if aula and aula.turma_id else None
        if turma:
            chave = f"{registro.data_aula.isoformat()}_turma_{turma.id}"
        elif aula:
            chave = f"aula_{aula.id}"
        else:
            chave = f"historico_{registro.id}"

        if chave not in agrupado:
            agrupado[chave] = {
                "data": registro.data_aula.isoformat(),
                "nome_exibicao": turma.nome_turma if turma else f"{aluno.nome} {aluno.sobrenome or ''}".strip(),
                "is_turma": bool(turma),
                "turma_id": turma.id if turma else None,
                "professor_nome": aula.professor.nome if aula and aula.professor else None,
                "alunos": [],
            }

        agrupado[chave]["alunos"].append({
            "historico_id": registro.id,
            "nome": f"{aluno.nome} {aluno.sobrenome or ''}".strip(),
            "status_presenca": bool(registro.status_presenca),
            "desempenho": registro.desempenho,
            "observacao": registro.observacao,
            "chamada_realizada": bool(registro.chamada_realizada),
        })

    return list(agrupado.values())
@router.get("/admin/estatisticas-mes")
def obter_estatisticas(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    hoje = agora_br()
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0)
    filtros_validos = (
        HistoricoAula.chamada_realizada.is_(True),
        HistoricoAula.data_aula >= inicio_mes,
        HistoricoAula.data_aula <= hoje,
        or_(
            and_(HistoricoAula.aula_id.is_not(None), Aula.status != StatusAula.cancelado),
            and_(
                HistoricoAula.aula_id.is_(None),
                ~func.lower(func.coalesce(HistoricoAula.observacao, "")).like("%cancelad%"),
            ),
        ),
    )

    base = db.query(HistoricoAula).outerjoin(
        Aula, HistoricoAula.aula_id == Aula.id
    ).filter(*filtros_validos)
    total = base.count()
    presencas = base.filter(HistoricoAula.status_presenca.is_(True)).count()
    faltosos = (
        db.query(Aluno.nome, func.count(HistoricoAula.id))
        .join(HistoricoAula, HistoricoAula.aluno_id == Aluno.id)
        .outerjoin(Aula, HistoricoAula.aula_id == Aula.id)
        .filter(*filtros_validos, HistoricoAula.status_presenca.is_(False))
        .group_by(Aluno.id, Aluno.nome)
        .order_by(func.count(HistoricoAula.id).desc())
        .limit(3)
        .all()
    )
    taxa = (presencas / total * 100) if total > 0 else 0
    return {
        "taxa_presenca": round(taxa, 1),
        "total_aulas": total,
        "alunos_faltosos": [{"nome": f[0], "faltas": f[1]} for f in faltosos],
    }

def remover_aula_completa(db: Session, aula: Aula, motivo: str = "", apagar_google: bool = True):
    """
    Helper para remocao completa e segura de uma Aula:
    - Garante remocao do evento Google apenas se nenhuma outra Aula ativa compartilha o mesmo google_event_id.
    - Apaga os registros de HistoricoAula vinculados (por aula_id ou fallback por aluno+data).
    - Apaga a Aula do banco de dados.
    """
    if apagar_google and aula.google_event_id:
        outras_aulas = db.query(Aula).filter(
            Aula.google_event_id == aula.google_event_id,
            Aula.id != aula.id,
            Aula.status.in_([StatusAula.marcada, StatusAula.presente]),
        ).count()
        if outras_aulas == 0:
            try:
                remover_evento_google(aula.google_event_id)
            except Exception as e:
                print(f"Aviso ao remover evento Google ({aula.google_event_id}): {e}")

    historicos = historicos_vinculados_a_aula(db, aula)

    for hist in historicos:
        db.delete(hist)

    db.delete(aula)


@router.delete("/cancelar-grupo")
def cancelar_aula_grupo(
    data_inicio: str = FastAPIQuery(...), 
    turma_id: Optional[int] = FastAPIQuery(None), 
    aluno_id: Optional[int] = FastAPIQuery(None), 
    db: Session = Depends(get_db), 
    usuario: str = Depends(verificar_token)
):
    try:
        limpo = data_inicio.replace('Z', '+00:00').split('.')[0]
        dt_inicio = datetime.fromisoformat(limpo)
    except Exception:
        raise HTTPException(status_code=400, detail="Data inválida")

    query = db.query(Aula).filter(Aula.data_inicio == dt_inicio)
    if turma_id:
        query = query.filter(Aula.turma_id == turma_id)
    elif aluno_id:
        query = query.filter(Aula.aluno_id == aluno_id)

    aulas = query.all()
    if not aulas:
        return {"msg": "Nada encontrado", "count": 0}

    count = 0
    for a in aulas:
        remover_aula_completa(db, a)
        count += 1

    db.commit()
    return {"msg": "Removido", "count": count}


@router.delete("/{aula_id}")
def deletar_aula(aula_id: int, db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada")
    remover_aula_completa(db, aula)
    db.commit()
    return {"msg": "Excluído"}


@router.post("/admin/sanear-orfaos")
def sanear_historicos_orfaos(db: Session = Depends(get_db), usuario: str = Depends(verificar_token)):
    orfaos_id = db.query(HistoricoAula).outerjoin(Aula, HistoricoAula.aula_id == Aula.id).filter(
        HistoricoAula.aula_id != None,
        Aula.id == None
    ).all()

    count = 0
    for h in orfaos_id:
        db.delete(h)
        count += 1

    vinculados = 0
    aulas_vinculadas = {row[0] for row in db.query(HistoricoAula.aula_id).filter(HistoricoAula.aula_id.is_not(None)).all()}
    pendentes_antigos = db.query(HistoricoAula).filter(
        HistoricoAula.chamada_realizada == False,
        HistoricoAula.aula_id == None
    ).all()

    for h in pendentes_antigos:
        candidatas = db.query(Aula).filter(
            Aula.aluno_id == h.aluno_id,
            func.date(Aula.data_inicio) == func.date(h.data_aula),
        ).order_by(Aula.data_inicio.asc(), Aula.id.asc()).all()
        disponiveis = [a for a in candidatas if a.id not in aulas_vinculadas]
        if disponiveis:
            exata = next((a for a in disponiveis if a.data_inicio == h.data_aula), None)
            escolhida = exata or disponiveis[0]
            h.aula_id = escolhida.id
            aulas_vinculadas.add(escolhida.id)
            vinculados += 1
        else:
            db.delete(h)
            count += 1

    db.commit()
    return {"status": "sucesso", "orfaos_removidos": count, "historicos_vinculados": vinculados}


@router.get("/historico/{aluno_id}")
def obter_historico_aluno(aluno_id: int, db: Session = Depends(get_db)):
    return db.query(Aula).filter(
        Aula.aluno_id == aluno_id, 
        Aula.status.in_([StatusAula.presente, StatusAula.ausente])
    ).order_by(Aula.data_inicio.desc()).all()


@router.get("/relatorio-aluno/{aluno_id}")
def obter_relatorio_pedagogico(aluno_id: int, db: Session = Depends(get_db)):
    historico = db.query(HistoricoAula).filter(HistoricoAula.aluno_id == aluno_id).order_by(HistoricoAula.data_aula.desc()).all()
    return [{"data": h.data_aula.strftime("%d/%m/%Y") if hasattr(h.data_aula, 'strftime') else str(h.data_aula), "presenca": "✅" if h.status_presenca is True else "❌", "desempenho": h.desempenho or "Sem avaliação", "observacao": h.observacao or "-"} for h in historico]