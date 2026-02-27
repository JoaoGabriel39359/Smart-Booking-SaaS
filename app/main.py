from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates # Importante para o Portal
from sqlalchemy.orm import Session
from app.routes import alunos, aulas, webhook, turmas 
from app.database import Base, engine, get_db
from app import models
from apscheduler.schedulers.background import BackgroundScheduler
from app.services.lembretes import verificar_lembretes
from datetime import datetime
import os

# Cria as tabelas no banco
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agenda SaaS")

# Configurações de Pastas
app.mount("/static", StaticFiles(directory="frontend"), name="static")
# Define onde estão os seus arquivos HTML (coloque o portal.html dentro de app/templates)
templates = Jinja2Templates(directory="app/templates")

# Inclusão de Rotas
app.include_router(turmas.router)
app.include_router(alunos.router)
app.include_router(aulas.router)
app.include_router(webhook.router) 

# --- SCHEDULER (Lembretes) ---
scheduler = BackgroundScheduler()
@app.on_event("startup")
def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(verificar_lembretes, "interval", minutes=30) # Aumentado para 30min para poupar recursos
        scheduler.start()

@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()

# --- ROTAS DE PÁGINAS (FRONTEND) ---

@app.get("/")
def home():
    return {"status": "SaaS de Agenda Online Rodando"}

# Painel do Professor (Continua estático como você deixou)
@app.get("/painel")
async def painel():
    return FileResponse("frontend/index.html")

# NOVO PORTAL DO ALUNO (Unificado: Ver, Cancelar e Agendar)
@app.get("/portal/{aluno_id}", response_class=HTMLResponse)
async def pagina_portal_aluno(aluno_id: int, request: Request, db: Session = Depends(get_db)):
    aluno = db.query(models.Aluno).filter(models.Aluno.id == aluno_id).first()
    if not aluno:
        return "Aluno não encontrado no sistema."

    # Busca aulas futuras marcadas para exibir na lista
    aulas_aluno = db.query(models.Aula).filter(
        models.Aula.aluno_id == aluno_id,
        models.Aula.status == "marcada",
        models.Aula.data_inicio >= datetime.now()
    ).order_by(models.Aula.data_inicio).all()

    # AJUSTE AQUI: No dicionário do contexto, vamos garantir que o 'tipo' seja o nome (string)
    # Isso resolve o problema de comparação no HTML de uma vez por todas
    contexto_aluno = {
        "id": aluno.id,
        "nome": aluno.nome,
        "sobrenome": aluno.sobrenome,
        "telefone": aluno.telefone,
        "email": aluno.email,
        "tipo": aluno.tipo.name if hasattr(aluno.tipo, 'name') else str(aluno.tipo),
        "creditos_reposicao": aluno.creditos_reposicao
    }

    return templates.TemplateResponse("portal.html", {
        "request": request,
        "aluno": contexto_aluno, # Enviamos o dicionário formatado
        "aulas": aulas_aluno
    })