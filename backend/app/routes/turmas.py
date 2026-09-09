from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from app.auth import verificar_token
from app.services.agenda_background import (
    remover_eventos_google_sem_referencia,
    sincronizar_agenda_completa,
    sincronizar_agenda_turma,
)
from sqlalchemy.orm import Session                     
from sqlalchemy import func, Time
from app.database import get_db          
from app.models import Turma, Aluno, Aula, HorarioAula, Professor, StatusAula, HistoricoAula
from app.core.config import agora_br
from app.routes.aulas import remover_aula_completa
from datetime import datetime

router = APIRouter(prefix="/turmas", tags=["turmas"])

LIMITES_POR_TIPO = {"VIP": 1, "DUO": 2, "TEAM": 6}
DIAS_EXTENSO = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


# --- CRIAR TURMA ---
@router.post("/")
def criar_turma(
    dados: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    try:
        limites = {"VIP": 1, "DUO": 2, "TEAM": 6}
        limite_max = limites.get(dados.get('tipo'), 6)

        professor_id = dados.get("professor_id")
        if professor_id is not None:
            professor = db.query(Professor).filter(Professor.id == int(professor_id), Professor.ativo.is_(True)).first()
            if not professor:
                raise HTTPException(status_code=400, detail="Professor inexistente ou inativo.")
            professor_id = professor.id
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
            meet_link=dados.get('meet_link'),
            professor_id=professor_id,
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

        background_tasks.add_task(sincronizar_agenda_turma, nova_turma.id)
        return {
            "status": "sucesso",
            "msg": f"Turma {nova_turma.nome_turma} criada!",
            "agenda_sincronizando": True,
        }

        
    except Exception as e:
        db.rollback()
        print(f"Erro crítico ao criar turma: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{turma_id}")
def editar_turma(
    turma_id: int,
    dados: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    """
    Edicao completa da turma: nome, meet, tipo, duracao, dias/horarios e alunos.

    Regra de ouro: NUNCA destruir credito de reposicao. Por isso a limpeza da agenda
    remove apenas aulas FUTURAS com status 'marcada'. Aulas canceladas (que sustentam o
    credito) e aulas ja realizadas (historico pedagogico) ficam intactas.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")

    agora = agora_br()

    try:
        # ---------- 1. Campos simples ----------
        if dados.get("nome_turma"):
            turma.nome_turma = dados["nome_turma"]
        if "meet_link" in dados:
            turma.meet_link = dados.get("meet_link") or None
        if "professor_id" in dados:
            professor_id = dados.get("professor_id")
            if professor_id is None:
                turma.professor_id = None
            else:
                professor = db.query(Professor).filter(
                    Professor.id == int(professor_id),
                    Professor.ativo.is_(True),
                ).first()
                if not professor:
                    raise HTTPException(status_code=400, detail="Professor inexistente ou inativo.")
                turma.professor_id = professor.id

        tipo_novo = dados.get("tipo") or turma.tipo
        limite_max = LIMITES_POR_TIPO.get(tipo_novo, 6)

        # ---------- 2. Alunos (valida capacidade ANTES de alterar nada) ----------
        ids_antigos = {a.id for a in turma.alunos}
        alunos_alterados = "aluno_ids" in dados

        if alunos_alterados:
            ids_novos = {int(i) for i in (dados.get("aluno_ids") or [])}
        else:
            ids_novos = set(ids_antigos)

        if len(ids_novos) > limite_max:
            raise HTTPException(
                status_code=400,
                detail=f"Turma do tipo {tipo_novo} aceita no máximo {limite_max} aluno(s). "
                       f"Você selecionou {len(ids_novos)}."
            )

        turma.tipo = tipo_novo
        turma.capacidade_maxima = limite_max
        if dados.get("duracao_minutos"):
            turma.duracao_minutos = int(dados["duracao_minutos"])

        # ---------- 3. Dias e horarios ----------
        horarios_alterados = "horarios" in dados
        if horarios_alterados:
            horarios_recebidos = dados.get("horarios") or []
            if not horarios_recebidos:
                raise HTTPException(status_code=400, detail="Informe ao menos um dia/horário para a turma.")

            novos_horarios = []
            for h in horarios_recebidos:
                try:
                    dia = int(h["dia"])
                    hora = datetime.strptime(h["hora"], "%H:%M").time()
                except (KeyError, TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"Horário inválido: {h}")
                if not 0 <= dia <= 6:
                    raise HTTPException(status_code=400, detail=f"Dia da semana inválido: {dia}")
                if (dia, hora) not in novos_horarios:
                    novos_horarios.append((dia, hora))

            novos_horarios.sort()
            turma.dia_semana = ", ".join(DIAS_EXTENSO[d] for d, _ in novos_horarios)
            turma.horario = ", ".join(hh.strftime("%H:%M") for _, hh in novos_horarios)

            db.query(HorarioAula).filter(HorarioAula.turma_id == turma_id).delete(synchronize_session="fetch")
            for dia, hora in novos_horarios:
                db.add(HorarioAula(turma_id=turma_id, dia_da_semana=dia, horario=hora))

        # ---------- 4. Aplica o vinculo dos alunos ----------
        if alunos_alterados:
            removidos = ids_antigos - ids_novos
            if removidos:
                db.query(Aluno).filter(Aluno.id.in_(removidos)).update(
                    {"turma_id": None}, synchronize_session=False
                )
            if ids_novos:
                for aluno in db.query(Aluno).filter(Aluno.id.in_(ids_novos)).all():
                    aluno.turma_id = turma_id
                    aluno.tipo = tipo_novo
        elif "tipo" in dados:
            for aluno in turma.alunos:
                aluno.tipo = tipo_novo

        db.flush()

        # ---------- 5. Regera a agenda futura, se algo estrutural mudou ----------
        precisa_regerar = (
            horarios_alterados
            or alunos_alterados
            or "duracao_minutos" in dados
            or "tipo" in dados
            or "professor_id" in dados
        )

        aulas_removidas = 0
        event_ids_removidos: set[str] = set()
        if precisa_regerar:
            # Pega tambem as aulas dos alunos que sairam: elas tem turma_id desta turma.
            aulas_futuras = db.query(Aula).filter(
                Aula.turma_id == turma_id,
                Aula.data_inicio >= agora,
                Aula.status == StatusAula.marcada,
            ).all()

            for aula in aulas_futuras:
                if aula.google_event_id:
                    event_ids_removidos.add(aula.google_event_id)
                remover_aula_completa(db, aula, motivo="Edição de turma", apagar_google=False)
                aulas_removidas += 1

        db.commit()

        if precisa_regerar:
            background_tasks.add_task(sincronizar_agenda_turma, turma_id, tuple(event_ids_removidos))

        return {
            "status": "sucesso",
            "msg": f"Turma {turma.nome_turma} atualizada!",
            "aulas_removidas": aulas_removidas,
            "agenda_sincronizando": precisa_regerar
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"ERRO AO EDITAR TURMA {turma_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao salvar: {str(e)}")

# --- GERAR MENSAL (VERSÃO UNIFICADA) ---
@router.post("/gerar-mensal")
def rota_gerar_mensal(
    background_tasks: BackgroundTasks,
    usuario: str = Depends(verificar_token),
):
    background_tasks.add_task(sincronizar_agenda_completa)
    return {
        "status": "sucesso",
        "msg": "Sincronização da agenda iniciada em segundo plano.",
    }

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
            "duracao_minutos": t.duracao_minutos,
            "meet_link": t.meet_link,
            "professor_id": t.professor_id,
            "professor_nome": t.professor.nome if t.professor else None,
            # Horarios estruturados: o modal de edicao precisa deles para pre-preencher
            "horarios": sorted(
                [{"dia": h.dia_da_semana, "hora": h.horario.strftime("%H:%M")} for h in t.horarios],
                key=lambda x: (x["dia"], x["hora"])
            ),
            "alunos": [{"id": a.id, "nome": a.nome, "sobrenome": a.sobrenome} for a in t.alunos]
        })
    return resultado

# --- DELETAR TURMA ---
@router.delete("/{turma_id}")
def deletar_turma(
    turma_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: str = Depends(verificar_token),
):
    try:
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        agora = agora_br()

        # 1. Alunos e horários da turma
        alunos = db.query(Aluno).filter(Aluno.turma_id == turma_id).all()
        alunos_ids = [a.id for a in alunos]
        horarios_turma = db.query(HorarioAula).filter(HorarioAula.turma_id == turma_id).all()

        # 2. Coletar Aulas da turma e Aulas órfãs (turma_id=NULL) dos mesmos alunos nos mesmos horários/dias da turma
        aulas_para_remover = []
        if alunos_ids:
            aulas_turma = db.query(Aula).filter(Aula.turma_id == turma_id).all()
            aulas_para_remover.extend(aulas_turma)

            if horarios_turma:
                for h in horarios_turma:
                    aulas_orfas = db.query(Aula).filter(
                        Aula.aluno_id.in_(alunos_ids),
                        Aula.turma_id == None,
                        func.extract('dow', Aula.data_inicio) == (h.dia_da_semana + 1) % 7,
                        func.cast(Aula.data_inicio, Time) == h.horario
                    ).all()
                    aulas_para_remover.extend(aulas_orfas)

        aulas_unicas = list({a.id: a for a in aulas_para_remover}.values())
        event_ids_removidos: set[str] = set()

        # Remove somente agendamentos futuros ainda não realizados.
        for aula in aulas_unicas:
            historico_realizado = db.query(HistoricoAula).filter(
                HistoricoAula.aula_id == aula.id,
                HistoricoAula.chamada_realizada.is_(True),
            ).first()
            preservar = (
                aula.data_inicio < agora
                or aula.status in (StatusAula.presente, StatusAula.ausente, StatusAula.cancelado)
                or historico_realizado is not None
            )
            if preservar:
                aula.turma_id = None
                continue

            if aula.google_event_id:
                event_ids_removidos.add(aula.google_event_id)
            remover_aula_completa(db, aula, apagar_google=False)

        if alunos_ids:

            # Desvincula alunos da turma (turma_id = NULL)
            db.query(Aluno).filter(Aluno.id.in_(alunos_ids)).update({"turma_id": None}, synchronize_session=False)

        # Limpar Horários Semanais
        db.query(HorarioAula).filter(HorarioAula.turma_id == turma_id).delete(synchronize_session=False)

        # Apagar a Turma
        db.delete(turma)

        db.commit()
        background_tasks.add_task(remover_eventos_google_sem_referencia, tuple(event_ids_removidos))
        return {"msg": "Turma e agendamentos deletados com sucesso!"}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"ERRO AO DELETAR TURMA: {str(e)}")
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