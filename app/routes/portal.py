import os
import pytz
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.google_calendar import criar_evento, remover_evento_google
from app.services.whatsapp import enviar_whatsapp
from app.services.agendamento import duracao_aula_minutos
from app.core.config import BASE_URL, agora_br

router = APIRouter(tags=["portal"])

ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(ROUTES_DIR)
BASE_DIR = os.path.dirname(APP_DIR)
TEMPLATES_PATH = os.path.join(BASE_DIR, "frontend", "templates")

templates = Jinja2Templates(directory=TEMPLATES_PATH)


@router.get("/")
def home():
    return {"status": "SaaS de Agenda Online Rodando"}


@router.get("/painel")
async def painel():
    caminho_index = os.path.join(BASE_DIR, "frontend", "index.html")
    if not os.path.exists(caminho_index):
        arquivos_na_raiz = os.listdir(BASE_DIR)
        return {
            "erro": "Arquivo não encontrado",
            "onde_procurei": caminho_index,
            "arquivos_que_existem_na_raiz": arquivos_na_raiz
        }
    return FileResponse(caminho_index)


@router.get("/portal/{token}", response_class=HTMLResponse)
async def pagina_portal_aluno(token: str, request: Request, db: Session = Depends(get_db)):
    agora = agora_br()

    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    if not aluno:
        return HTMLResponse(content="Link de acesso inválido ou expirado.", status_code=404)

    filtro_hora = agora - timedelta(hours=6)

    aulas_aluno = db.query(models.Aula).filter(
        models.Aula.aluno_id == aluno.id,
        models.Aula.status.in_(["marcada", models.StatusAula.marcada]),
        models.Aula.data_inicio >= filtro_hora
    ).order_by(models.Aula.data_inicio).all()

    contexto_aluno = {
        "id": aluno.id,
        "nome": aluno.nome,
        "sobrenome": aluno.sobrenome,
        "telefone": aluno.telefone,
        "email": aluno.email,
        "token": aluno.token_acesso, 
        "tipo": aluno.tipo.name if hasattr(aluno.tipo, 'name') else str(aluno.tipo),
        "creditos_reposicao": aluno.creditos_reposicao
    }

    return templates.TemplateResponse(request, "portal.html", {
        "aluno": contexto_aluno, 
        "aulas": aulas_aluno
    })


@router.post("/reagendar/{token}")
async def reagendar_aula(
    token: str, 
    background_tasks: BackgroundTasks,
    aula_id: int = Form(...), 
    nova_data: str = Form(...), 
    grade_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    if not aluno:
        return "Acesso negado: Token inválido."

    try:
        try:
            nova_data_limpa = nova_data.replace("T", " ")
            if len(nova_data_limpa) == 16:
                data_dt = datetime.strptime(nova_data_limpa, "%Y-%m-%d %H:%M")
            else:
                data_dt = datetime.fromisoformat(nova_data.replace("Z", ""))
        except Exception as e:
            print(f"❌ Erro na conversão de data: {nova_data} -> {e}")
            return f"Erro no formato da data enviada: {nova_data}"

        data_fim_dt = data_dt + timedelta(minutes=duracao_aula_minutos(db, aluno))

        professor_id = None
        prof_nome = None
        if grade_id:
            turno_ref = db.query(models.GradeProfessor).filter(models.GradeProfessor.id == grade_id).first()
            if turno_ref and turno_ref.professor_id:
                professor_id = turno_ref.professor_id
                prof_obj = db.query(models.Professor).filter(models.Professor.id == professor_id).first()
                if prof_obj:
                    prof_nome = prof_obj.nome
        elif aluno.turma_id and aluno.turma and aluno.turma.professor_id:
            professor_id = aluno.turma.professor_id
            if aluno.turma.professor:
                prof_nome = aluno.turma.professor.nome

        if aula_id == 0:
            if aluno.creditos_reposicao <= 0:
                return HTMLResponse(content="Erro: Você não possui créditos de reposição.", status_code=400)
            
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
            aluno.creditos_reposicao -= 1
            db.add(nova_aula)

        else:
            aula = db.query(models.Aula).filter(
                models.Aula.id == aula_id, 
                models.Aula.aluno_id == aluno.id
            ).first()

            if not aula:
                return "Erro: Aula não encontrada."

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

        return RedirectResponse(url=f"/portal/{token}?sucesso=true", status_code=303)

    except Exception as e:
        db.rollback()
        print(f"❌ Erro no servidor: {e}")
        return HTMLResponse(content=f"Erro ao processar agendamento: {str(e)}", status_code=500)
