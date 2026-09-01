import os
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from app.database import Base, engine
from app.routes import alunos, aulas, webhook, turmas, auth, portal, relatorios, professores
from app.services import lembretes
from app.services.lembretes import verificar_lembretes_background
from app.services.gerar_agenda import gerar_aulas_da_semana

# --- LÓGICA DE CAMINHOS ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
FRONTEND_PATH = os.path.join(BASE_DIR, "frontend")
STATIC_PATH = os.path.join(FRONTEND_PATH, "static")


# --- AGENDADOR (SCHEDULER) ---
scheduler = BackgroundScheduler()
scheduler.add_job(verificar_lembretes_background, 'interval', minutes=1)
scheduler.add_job(gerar_aulas_da_semana, 'cron', day_of_week='mon', hour=0, minute=0)

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Sistema Agenda SaaS Iniciado")
    if not scheduler.running:
        scheduler.start()
    # Cria as tabelas ao iniciar se não existirem
    Base.metadata.create_all(bind=engine)
    yield
    print("🛑 Sistema Encerrado")
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(title="Agenda SaaS", lifespan=lifespan)

# --- MIDDLEWARE / STATIC ---
if os.path.exists(STATIC_PATH):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

if os.path.exists(FRONTEND_PATH):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_PATH), name="frontend")

# --- REGISTRO DE ROTAS ---
app.include_router(portal.router)
app.include_router(auth.router)
app.include_router(turmas.router)
app.include_router(alunos.router)
app.include_router(aulas.router)
app.include_router(webhook.router)
app.include_router(lembretes.router)
app.include_router(relatorios.router)
app.include_router(professores.router)
