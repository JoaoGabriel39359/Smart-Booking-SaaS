import traceback
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.services.whatsapp import enviar_whatsapp
from app.database import SessionLocal, get_db
from app.services.google_calendar import criar_evento, remover_evento_google
from app import models
from app.models import Aluno, Aula, GradeProfessor, StatusAula, TipoAluno # Importado TipoAluno
from datetime import datetime, timedelta, time

TELEFONE_PROFESSOR = "5524998739359"
router = APIRouter(prefix="/aulas", tags=["aulas"])


# ==============================
# MARCAR AULA
# ==============================
@router.post("/marcar")
def marcar_aula(aluno_id: int, data: str, hora: str, eh_reposicao: bool = False, db: Session = Depends(get_db)):
    try:
        # 1. Verificar se o aluno existe
        aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # converter data e hora
        try:
            inicio = datetime.strptime(f"{data.strip()} {hora.strip()}", "%d-%m-%Y %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de data ou hora inválido.")

        fim = inicio + timedelta(hours=1)

        # 2. DEFINIR QUEM VAI PARA A AULA
        lista_alunos = [aluno]
        if aluno.turma_id and aluno.tipo != "VIP":
            colegas = db.query(Aluno).filter(Aluno.turma_id == aluno.turma_id, Aluno.id != aluno.id).all()
            lista_alunos.extend(colegas)

        # 3. VALIDAÇÕES DE REGRAS DE NEGÓCIO
        for pessoinha in lista_alunos:
            if eh_reposicao:
                # VERIFICAÇÃO DE VALIDADE: Conta créditos 'cancelado' dentro dos 30 dias
                creditos_reais = db.query(Aula).filter(
                    Aula.aluno_id == pessoinha.id,
                    Aula.status == "cancelado",
                    Aula.validade_reposicao >= datetime.now()
                ).count()

                if creditos_reais <= 0:
                    # Sincroniza o contador do aluno caso esteja inconsistente
                    pessoinha.creditos_reposicao = 0 
                    db.commit()
                    raise HTTPException(
                        status_code=400, 
                        detail=f"O aluno {pessoinha.nome} não possui créditos válidos (expirados ou inexistentes)."
                    )
            else:
                # Regra normal de limite semanal
                uma_semana_atras = inicio - timedelta(days=7)
                aulas_na_semana = db.query(Aula).filter(
                    Aula.aluno_id == pessoinha.id,
                    Aula.data_inicio >= uma_semana_atras,
                    Aula.status == "marcada"
                ).count()
                
                limite = pessoinha.limite_aulas_semana or 1
                if aulas_na_semana >= limite:
                    raise HTTPException(status_code=400, detail=f"Limite de {pessoinha.nome} atingido.")

        # 4. Verificar conflito de horário
        conflito = db.query(Aula).filter(
            Aula.data_inicio < fim,
            Aula.data_fim > inicio,
            Aula.status.in_(["marcada", "presente"]) 
        ).first()

        if conflito:
            raise HTTPException(status_code=400, detail="Este horário já está ocupado.")

        # 5. GOOGLE CALENDAR (Definição da variável g_id para tirar o amarelo)
        g_id = None  
        titulo_aula = f"Aula: {aluno.nome}" if len(lista_alunos) == 1 else f"Aula Turma: {aluno.turma.nome if aluno.turma else 'Coletiva'}"
        try:
            g_id = criar_evento(inicio, fim, titulo_aula)
        except Exception as ge:
            print(f"DEBUG: Falha Google Calendar: {ge}")

        # 6. Salvar no banco para TODOS os alunos da lista
        novas_aulas = []
        for p in lista_alunos:
            data_validade = None
            
            if eh_reposicao:
                if p.creditos_reposicao > 0:
                    p.creditos_reposicao -= 1
                
                credito_para_consumir = db.query(Aula).filter(
                    Aula.aluno_id == p.id,
                    Aula.status == "cancelado",
                    Aula.validade_reposicao >= datetime.now()
                ).order_by(Aula.validade_reposicao.asc()).first()
                
                if credito_para_consumir:
                    data_validade = credito_para_consumir.validade_reposicao
                    credito_para_consumir.status = "presente" 

            nova = Aula(
                aluno_id=p.id,
                data_inicio=inicio,
                data_fim=fim,
                status="marcada", 
                google_event_id=g_id,
                eh_reposicao=eh_reposicao,
                validade_reposicao=data_validade,
                lembrete_enviado=False # Inicializa como falso
            )
            novas_aulas.append(nova)

        db.add_all(novas_aulas)
        db.commit()

        # === NOVIDADE: Enviar WhatsApp de Confirmação ===
        for aula_criada in novas_aulas:
            try:
                msg_confirmacao = (
                    f"Agendado com sucesso, {aula_criada.aluno.nome}! ✅\n\n"
                    f"Sua aula será dia {aula_criada.data_inicio.strftime('%d/%m')} "
                    f"às {aula_criada.data_inicio.strftime('%H:%M')}.\n"
                    f"{'★ Aula de Reposição' if eh_reposicao else ''}"
                )
                enviar_whatsapp(aula_criada.aluno.telefone, msg_confirmacao)
            except Exception as e:
                print(f"Erro ao avisar aluno no Zap: {e}")

        return {"status": "sucesso", "event_id": g_id}

    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro técnico interno.")

@router.post("/avulsa")
async def criar_aula_avulsa(dados: dict, db: Session = Depends(get_db)):
    try:
        aluno_id = int(dados['aluno_id'])
        aluno = db.query(models.Aluno).filter(models.Aluno.id == aluno_id).first()
        
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        inicio = datetime.fromisoformat(dados['data_inicio'])
        fim = inicio + timedelta(hours=1)

        # --- INTEGRAÇÃO COM GOOGLE CALENDAR ---
        google_event_id = None
        titulo_aula = f"Aula VIP: {aluno.nome} {aluno.sobrenome or ''}"
        
        try:
            # Chama a função que você já tem configurada no seu projeto
            google_event_id = criar_evento(inicio, fim, titulo_aula)
        except Exception as ge:
            print(f"DEBUG: Falha ao sincronizar com Google Calendar: {ge}")
        # ---------------------------------------

        nova_aula = models.Aula(
            aluno_id=aluno_id,
            data_inicio=inicio,
            data_fim=fim,
            turma_id=None,
            status="marcada",
            google_event_id=google_event_id  # Salva o ID do Google para permitir cancelar depois
        )

        db.add(nova_aula)
        db.commit()
        db.refresh(nova_aula)
        
        return {"msg": "Aula agendada e sincronizada com Google Agenda!", "id": nova_aula.id}
    
    except Exception as e:
        db.rollback()
        print(f"Erro ao agendar avulsa: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao agendar: {str(e)}")

# ==============================
# LISTAR AULAS
# ==============================
@router.get("/")
def listar_aulas():
    db = SessionLocal()
    aulas = db.query(Aula).order_by(Aula.data_inicio).all()

    resultado = []

    for a in aulas:
        resultado.append({
            "id": a.id,
            "aluno_id": a.aluno_id,
            "data_inicio": a.data_inicio,
            "data_fim": a.data_fim,
            "status": a.status,
            "google_event_id": a.google_event_id
        })

    db.close()
    return resultado


# ==============================
# HORÁRIOS LIVRES
# ==============================
from sqlalchemy import func

@router.get("/horarios-livres")
def horarios_livres(data: str, token: str = None, db: Session = Depends(get_db)):
    db = SessionLocal()

    try:
        data_base = datetime.strptime(data, "%d-%m-%Y")
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Formato de data inválido")

    # --- NOVO: VERIFICAR SE A TURMA DO ALUNO JÁ TEM AULA ---
    if token:
        aluno = db.query(Aluno).filter(Aluno.token_acesso == token).first()
        if aluno and aluno.turma_id:
            # Busca se existe alguma aula marcada para qualquer aluno desta mesma turma neste dia
            aula_turma = db.query(Aula).join(Aluno).filter(
                Aluno.turma_id == aluno.turma_id,
                func.date(Aula.data_inicio) == data_base.date(),
                Aula.status == "marcada"
            ).first()

            if aula_turma:
                db.close()
                return {
                    "aula_marcada_pela_turma": True,
                    "horario_turma": aula_turma.data_inicio.strftime("%H:%M"),
                    "horarios_livres": []
                }

    # --- BUSCAR A GRADE DO PROFESSOR (Igual ao seu) ---
    dia_semana_atual = data_base.weekday()
    turnos_professor = db.query(GradeProfessor).filter(
        GradeProfessor.dia_semana == dia_semana_atual,
        GradeProfessor.ativo == True
    ).all()

    if not turnos_professor:
        db.close()
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

    # --- FILTRAR HORÁRIOS OCUPADOS ---
    # Aqui uma pequena melhoria: se 1 aluno da turma marcou, o horário está ocupado para todos
    inicio_dia = datetime.combine(data_base, time(0, 0))
    fim_dia = datetime.combine(data_base, time(23, 59))

    aulas_marcadas = db.query(Aula).filter(
        Aula.data_inicio >= inicio_dia,
        Aula.data_inicio <= fim_dia,
        Aula.status == "marcada"
    ).all()

    horarios_ocupados = [a.data_inicio for a in aulas_marcadas]

    livres = []
    for h in horarios_possiveis:
        if h not in horarios_ocupados:
            # Evita mostrar horários passados se a data for hoje
            if h > datetime.now():
                livres.append(h.strftime("%H:%M"))

    db.close()
    return {
        "data": data,
        "horarios_livres": sorted(list(set(livres)))
    }

# ==============================
# CANCELAR AULA
# ==============================
# Mantenha seus imports originais no topo

@router.post("/{aula_id}/cancelar/{token}")
def cancelar_aula(aula_id: int, token: str, db: Session = Depends(get_db)): # <--- ADICIONEI 'token: str' AQUI
    agora = datetime.now()
    
    # 1. Busca a aula específica (Alterado para validar o TOKEN)
    aula = db.query(Aula).join(Aluno).filter(
        Aula.id == aula_id,
        Aluno.token_acesso == token # <--- ADICIONEI ESTA LINHA AQUI
    ).first()
    
    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada ou acesso negado.")

    aluno = aula.aluno
    inicio_aula = aula.data_inicio

    # 🚀 TRAVA DE SEGURANÇA: APENAS VIP CANCELA
    if aluno.tipo != TipoAluno.VIP:
        raise HTTPException(
        status_code=403,
        detail="Seu plano não permite cancelamento. Apenas alunos VIP possuem este direito."
    )

    # 2. Lógica de Antecedência (2 horas)
    gera_reposicao = (inicio_aula - agora) >= timedelta(hours=2)
    novo_status = "cancelado" if gera_reposicao else "ausente"

    # 3. Remover do Google Agenda
    if aula.google_event_id:
        try:
            remover_evento_google(aula.google_event_id)
        except Exception as e:
            print(f"Erro ao remover do Google: {e}")

    # 4. Atualizar os dados do Aluno no Banco
    aula.status = novo_status
    aula.google_event_id = None 
    
    validade_formatada = None # Iniciamos vazia

    if gera_reposicao:
        aluno.creditos_reposicao += 1
        # Calculamos e salvamos a validade de 30 dias
        data_validade = agora + timedelta(days=30)
        aula.validade_reposicao = data_validade
        validade_formatada = data_validade.strftime('%d/%m/%Y')

    db.commit()

    # 5. Notificação WhatsApp (Personalizada com a validade)
    link_portal = f"https://pseudoheroic-semispontaneous-gerda.ngrok-free.dev/portal/{aluno.token_acesso}"
    
    if gera_reposicao:
        msg = (
            f"Olá {aluno.nome}! ⚠️\n\n"
            f"Sua aula de *{inicio_aula.strftime('%d/%m às %H:%M')}* foi cancelada.\n"
            f"✅ *Um crédito de reposição foi adicionado à sua conta.*\n"
            f"⏳ Esse crédito é válido por 30 dias (vencimento em: *{validade_formatada}*).\n\n"
            f"Acesse o site para agendar sua reposição quando desejar!"
        )
    else:
        msg = (
            f"Olá {aluno.nome}! ⚠️\n\n"
            f"Sua aula de *{inicio_aula.strftime('%d/%m às %H:%M')}* foi cancelada.\n"
            f"❌ *Atenção:* Como o cancelamento foi feito com menos de 2h de antecedência, não houve geração de crédito de reposição conforme a política do plano VIP."
            f"Dúvidas? Acesse nosso portal: {link_portal}"
        )
    
    try:
        enviar_whatsapp(aluno.telefone, msg)
    except Exception as we:
        print(f"Erro WhatsApp: {we}")

    return {
        "msg": "Aula cancelada com sucesso", 
        "reembolso": gera_reposicao,
        "novo_status": novo_status,
        "validade": validade_formatada # Agora retorna a data para o frontend também
    }

@router.post("/configurar-grade")
def configurar_grade(dia: int, inicio: str, fim: str, db: Session = Depends(get_db)):
    """
    dia: 0 (Segunda) a 6 (Domingo)
    inicio/fim: "08:00", "18:00"
    """
    nova_grade = GradeProfessor(
        dia_semana=dia, 
        hora_inicio=inicio, 
        hora_fim=fim, 
        ativo=True
    )
    db.add(nova_grade)
    db.commit()
    return {"msg": f"Turno configurado para o dia {dia}"}

@router.get("/grade")
def listar_grade(db: Session = Depends(get_db)):
    """Retorna todos os turnos cadastrados para o professor"""
    return db.query(GradeProfessor).all()

@router.delete("/grade/{id}")
def deletar_grade(id: int, db: Session = Depends(get_db)):
    """Remove um turno específico da grade"""
    turno = db.query(GradeProfessor).filter(GradeProfessor.id == id).first()
    if not turno:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    db.delete(turno)
    db.commit()
    return {"msg": "Turno removido com sucesso"}

from datetime import datetime

@router.get("/lista-professor")
def listar_aulas_professor(db: Session = Depends(get_db)):
    agora = datetime.now()
    
    resultados = db.query(Aula, Aluno).\
        join(Aluno, Aula.aluno_id == Aluno.id).\
        filter(Aula.data_fim >= agora - timedelta(hours=3)).\
        filter(Aula.status == "marcada").\
        order_by(Aula.data_inicio.asc()).all()
    
    agrupado = {}

    for aula, aluno in resultados:
        chave = f"{aula.data_inicio.isoformat()}_{aula.turma_id or f'vip_{aluno.id}'}"
        
        if chave not in agrupado:
            agrupado[chave] = {
                "data_inicio": aula.data_inicio.isoformat(),
                "turma_id": aula.turma_id, # <--- LINHA ESSENCIAL ADICIONADA AQUI
                "status": aula.status,
                "nome_exibicao": aula.turma.nome_turma if aula.turma_id else f"{aluno.nome} {aluno.sobrenome or ''}",
                "tipo": aula.turma.tipo if aula.turma_id else aluno.tipo.name if hasattr(aluno.tipo, 'name') else str(aluno.tipo),
                "is_turma": True if aula.turma_id else False,
                "validade_reposicao": aula.validade_reposicao.isoformat() if aula.validade_reposicao else None,
                "alunos": []
            }
        
        agrupado[chave]["alunos"].append({
            "aula_id": aula.id,
            "aluno_id": aluno.id,
            "nome": f"{aluno.nome} {aluno.sobrenome or ''}"
        })

    return list(agrupado.values())

# ==============================
# DELETAR AULA (PAINEL PROFESSOR)
# ==============================
@router.delete("/{aula_id}")
def deletar_aula(aula_id: int, db: Session = Depends(get_db)):
    try:
        # 1. Busca a aula no banco
        aula = db.query(models.Aula).filter(models.Aula.id == aula_id).first()
        
        if not aula:
            raise HTTPException(status_code=404, detail="Aula não encontrada para exclusão.")

        # 2. Se a aula tiver um evento no Google Agenda, removemos de lá
        if aula.google_event_id:
            try:
                remover_evento_google(aula.google_event_id)
            except Exception as ge:
                print(f"DEBUG: Erro ao remover do Google Calendar: {ge}")

        # 3. Exclui o registro do banco de dados
        db.delete(aula)
        db.commit()

        return {"msg": "Aula excluída com sucesso da agenda e do banco!"}

    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Erro ao tentar excluir a aula.")

# --- ROTA DE HISTÓRICO ---
@router.get("/historico/{aluno_id}")
def obter_historico_aluno(aluno_id: int, db: Session = Depends(get_db)):
    # Buscamos os status que o banco aceita
    historico = db.query(Aula).filter(
        Aula.aluno_id == aluno_id,
        Aula.status.in_(['presente', 'ausente', 'Presente', 'Ausente'])
    ).order_by(Aula.data_inicio.desc()).all()
    
    return historico

# --- ROTA DE PRESENÇA ---
@router.patch("/{aula_id}/presenca")
def marcar_presenca(
    aula_id: int, 
    status: str, 
    desempenho: str, 
    observacoes: str = "", 
    db: Session = Depends(get_db)
):
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula não encontrada")

    status_valido = status.lower() 
    
    aula.status = status_valido 
    aula.desempenho = desempenho
    aula.observacoes = observacoes
    
    db.commit()
    return {"msg": "Presença registrada com sucesso!"}

@router.delete("/cancelar-grupo")
def cancelar_aula_grupo(
    data_inicio: str, 
    turma_id: Optional[int] = None, 
    aluno_id: Optional[int] = None, 
    db: Session = Depends(get_db)
):
    try:
        # O fromisoformat lida bem com o "Z" ou "+00:00" que o JS envia
        dt_inicio = datetime.fromisoformat(data_inicio.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido.")

    query = db.query(Aula).filter(Aula.data_inicio == dt_inicio)

    # Prioridade para Turma, depois Aluno individual
    if turma_id:
        query = query.filter(Aula.turma_id == turma_id)
    elif aluno_id:
        query = query.filter(Aula.aluno_id == aluno_id)
    else:
        raise HTTPException(status_code=400, detail="É necessário informar turma_id ou aluno_id.")

    aulas_para_cancelar = query.all()

    if not aulas_para_cancelar:
        return {"msg": "Nenhuma aula encontrada (talvez já tenha sido removida).", "count": 0}

    for aula in aulas_para_cancelar:
        # Se você tiver integração com Google Calendar, delete aqui também
        # if aula.google_event_id: remover_evento_google(aula.google_event_id)
        db.delete(aula)

    db.commit()
    return {"msg": "Cancelamento realizado", "count": len(aulas_para_cancelar)}