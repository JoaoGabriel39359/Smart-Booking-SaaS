from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.google_calendar import criar_evento, remover_evento_google
from app.services.whatsapp import enviar_whatsapp
from app.services.agendamento import duracao_aula_minutos
from app.services.creditos import consumir_credito, sincronizar_contador_creditos
from app.services.disponibilidade import resolver_grade_disponivel
from app.core.config import BASE_URL, agora_br
from app.core.paths import FRONTEND_INDEX

router = APIRouter(tags=["portal"])

@router.get("/")
def home():
    return {"status": "SaaS de Agenda Online Rodando"}


@router.get("/painel")
async def painel():
    if not FRONTEND_INDEX.is_file():
        return HTMLResponse("Frontend não encontrado.", status_code=404)
    return FileResponse(FRONTEND_INDEX)


@router.get("/portal/{token}", response_class=HTMLResponse)
async def pagina_portal_aluno(token: str, db: Session = Depends(get_db)):
    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    if not aluno:
        return HTMLResponse(content="Link de acesso inválido ou expirado.", status_code=404)
    if not FRONTEND_INDEX.is_file():
        return HTMLResponse("Frontend não encontrado.", status_code=404)
    return FileResponse(FRONTEND_INDEX)




@router.get("/api/portal/{token}")
def dados_portal_aluno(token: str, db: Session = Depends(get_db)):
    agora = agora_br()
    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Link de acesso inválido ou expirado.")

    sincronizar_contador_creditos(db, aluno, agora)
    aulas = db.query(models.Aula).filter(
        models.Aula.aluno_id == aluno.id,
        models.Aula.status == models.StatusAula.marcada,
        models.Aula.data_inicio >= agora - timedelta(hours=6),
    ).order_by(models.Aula.data_inicio).all()
    db.commit()

    return {
        "aluno": {
            "id": aluno.id,
            "nome": aluno.nome,
            "sobrenome": aluno.sobrenome,
            "telefone": aluno.telefone,
            "email": aluno.email,
            "token": aluno.token_acesso,
            "tipo": aluno.tipo.name if hasattr(aluno.tipo, "name") else str(aluno.tipo),
            "creditos_reposicao": aluno.creditos_reposicao,
        },
        "aulas": [
            {
                "id": aula.id,
                "data_inicio": aula.data_inicio.isoformat(),
                "data_fim": aula.data_fim.isoformat() if aula.data_fim else None,
                "eh_reposicao": bool(aula.eh_reposicao),
                "professor_nome": aula.professor.nome if aula.professor else None,
            }
            for aula in aulas
        ],
    }

@router.post("/reagendar/{token}")
async def reagendar_aula(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    aula_id: int = Form(...), 
    nova_data: str = Form(...), 
    grade_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Token inválido.")

    try:
        try:
            nova_data_limpa = nova_data.replace("T", " ")
            if len(nova_data_limpa) == 16:
                data_dt = datetime.strptime(nova_data_limpa, "%Y-%m-%d %H:%M")
            else:
                data_dt = datetime.fromisoformat(nova_data.replace("Z", ""))
        except Exception as e:
            print(f"❌ Erro na conversão de data: {nova_data} -> {e}")
            raise HTTPException(status_code=400, detail="Formato de data inválido.")

        data_fim_dt = data_dt + timedelta(minutes=duracao_aula_minutos(db, aluno))

        if data_dt <= agora_br():
            raise HTTPException(status_code=400, detail="Escolha um horário futuro.")

        turno_ref = resolver_grade_disponivel(
            db,
            data_dt,
            data_fim_dt,
            grade_id_preferida=grade_id,
            bloquear=True,
        )
        if not turno_ref:
            raise HTTPException(status_code=409, detail="Este horário acabou de ficar indisponível.")

        professor_id = turno_ref.professor_id
        prof_nome = turno_ref.professor.nome if turno_ref.professor else None

        if aula_id == 0:
            consumir_credito(db, aluno)
            
            g_id = None
            try:
                titulo = f"Reposição: {aluno.nome}"
                g_res = criar_evento(data_dt, data_fim_dt, titulo)
                g_id = g_res[0] if isinstance(g_res, tuple) else g_res
            except Exception as ge:
                print(f"⚠️ Erro Google Calendar: {ge}")

            nova_aula = models.Aula(
                aluno_id=aluno.id,
                professor_id=professor_id,
                data_inicio=data_dt,
                data_fim=data_fim_dt, 
                status=models.StatusAula.marcada,
                eh_reposicao=True,
                google_event_id=g_id, 
                lembrete_enviado=False
            )
            db.add(nova_aula)
            db.flush()
            db.add(models.HistoricoAula(
                aula_id=nova_aula.id,
                aluno_id=aluno.id,
                data_aula=data_dt,
                status_presenca=False,
                chamada_realizada=False,
                observacao="Aula de reposição agendada pelo portal",
                google_event_id=g_id,
            ))

        else:
            aula = db.query(models.Aula).filter(
                models.Aula.id == aula_id, 
                models.Aula.aluno_id == aluno.id
            ).first()

            if not aula:
                raise HTTPException(status_code=404, detail="Aula não encontrada.")

            try:
                if aula.google_event_id:
                    remover_evento_google(aula.google_event_id)
                
                titulo = f"Aula: {aluno.nome} (Reagendada)"
                g_res = criar_evento(data_dt, data_fim_dt, titulo)
                g_id = g_res[0] if isinstance(g_res, tuple) else g_res
                aula.google_event_id = g_id
            except Exception as ge:
                print(f"⚠️ Erro Google Calendar (Update): {ge}")

            aula.professor_id = professor_id
            aula.data_inicio = data_dt
            aula.data_fim = data_fim_dt
            aula.status = models.StatusAula.marcada
            aula.lembrete_enviado = False

        db.commit()
        link_portal = f"{BASE_URL}/portal/{token}"
        msg_reagendado = (
            f"Tudo certo, {aluno.nome}! ✅\n"
            f"Sua aula foi remarcada para: *{data_dt.strftime('%d/%m às %H:%M')}*.\n"
        )
        if prof_nome:
            msg_reagendado += f"Reposição agendada com o professor {prof_nome}.\n"
        msg_reagendado += f"\nVeja seus horários no portal:\n{link_portal}"

        background_tasks.add_task(enviar_whatsapp, aluno.telefone, msg_reagendado)

        if "application/json" in request.headers.get("accept", ""):
            return {
                "status": "sucesso",
                "creditos_reposicao": aluno.creditos_reposicao,
            }
        return RedirectResponse(url=f"/portal/{token}?sucesso=true", status_code=303)

    except HTTPException as e:
        db.rollback()
        if "application/json" in request.headers.get("accept", ""):
            raise
        return HTMLResponse(content=f"Erro: {e.detail}", status_code=e.status_code)
    except Exception as e:
        db.rollback()
        print(f"❌ Erro no servidor: {e}")
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=500, detail="Erro interno ao reagendar.")
        return HTMLResponse(content=f"Erro ao processar agendamento: {str(e)}", status_code=500)
