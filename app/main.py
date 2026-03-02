from fastapi import FastAPI, Request, Depends, Form
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from app.services.google_calendar import criar_evento, remover_evento_google
from fastapi.templating import Jinja2Templates # Importante para o Portal
from sqlalchemy.orm import Session
from app.routes import alunos, aulas, webhook, turmas 
from app.database import Base, engine, get_db
from app import models
from apscheduler.schedulers.background import BackgroundScheduler
from app.services.lembretes import verificar_lembretes
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles
import os

# Cria as tabelas no banco
Base.metadata.create_all(bind=engine)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: O que o sistema faz ao ligar
    print("🚀 Sistema Agenda SaaS Iniciado")
    if not scheduler.running:
        scheduler.start()
    yield
    # Shutdown: O que o sistema faz ao desligar
    print("🛑 Sistema Encerrado")
    if scheduler.running:
        scheduler.shutdown()

# JUNTE AS CONFIGURAÇÕES AQUI:
app = FastAPI(
    title="Agenda SaaS", 
    lifespan=lifespan
)

# Configurações de Pastas
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "app", "static")), name="static")
app.mount("/frontend", StaticFiles(directory=os.path.join(BASE_DIR, "frontend")), name="frontend")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "app", "templates"))

# Inclusão de Rotas
app.include_router(turmas.router)
app.include_router(alunos.router)
app.include_router(aulas.router)
app.include_router(webhook.router) 

# --- SCHEDULER (Lembretes) ---
scheduler = BackgroundScheduler()
scheduler.add_job(verificar_lembretes, 'interval', minutes=1)

# --- ROTAS DE PÁGINAS (FRONTEND) ---

@app.get("/")
def home():
    return {"status": "SaaS de Agenda Online Rodando"}

# Painel do Professor 
@app.get("/painel")
async def painel():
    caminho_index = os.path.join(BASE_DIR, "frontend", "index.html")
    return FileResponse(caminho_index)

# NOVO PORTAL DO ALUNO (Unificado: Ver, Cancelar e Agendar)
@app.get("/portal/{token}", response_class=HTMLResponse)
async def pagina_portal_aluno(token: str, request: Request, db: Session = Depends(get_db)):
    # Agora buscamos o aluno pelo token_acesso em vez do ID
    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    
    if not aluno:
        return HTMLResponse(content="Link de acesso inválido ou expirado.", status_code=404)

    # Busca aulas futuras usando o ID do aluno encontrado pelo token
    aulas_aluno = db.query(models.Aula).filter(
        models.Aula.aluno_id == aluno.id,
        models.Aula.status == "marcada",
        models.Aula.data_inicio >= datetime.now()
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

@app.post("/reagendar/{token}")
async def reagendar_aula(
    token: str, 
    aula_id: int = Form(...), 
    nova_data: str = Form(...), 
    db: Session = Depends(get_db)
):
    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    if not aluno:
        return "Acesso negado: Token inválido."

    try:
        # 1. Converte a data e define o fim da aula (1 hora depois)
        data_dt = datetime.strptime(nova_data, "%Y-%m-%dT%H:%M")
        data_fim_dt = data_dt + timedelta(hours=1)

        if aula_id == 0:  # Nova aula
            inicio_semana = data_dt - timedelta(days=data_dt.weekday())
            fim_semana = inicio_semana + timedelta(days=6, hours=23, minutes=59)

            contagem = db.query(models.Aula).filter(
                models.Aula.aluno_id == aluno.id,
                models.Aula.status == "marcada",
                models.Aula.data_inicio >= inicio_semana,
                models.Aula.data_inicio <= fim_semana
            ).count()

            if contagem >= (aluno.limite_aulas_semana or 1):
                return f"Erro: Você já atingiu seu limite de {aluno.limite_aulas_semana} aulas para esta semana."

            if aluno.creditos_reposicao <= 0:
                return "Erro: Você não possui créditos de reposição suficientes."
        
        g_id = None # Variável para guardar o ID do Google

        # --- CASO A: NOVA REPOSIÇÃO (Criar no Google) ---
        if aula_id == 0:
            if aluno.creditos_reposicao <= 0:
                return "Erro: Você não possui créditos de reposição suficientes."
            
            # Tenta criar no Google Calendar primeiro
            try:
                titulo = f"Reposição: {aluno.nome}"
                g_id = criar_evento(data_dt, data_fim_dt, titulo)
            except Exception as ge:
                print(f"⚠️ Erro Google Calendar (Novo): {ge}")

            nova_aula = models.Aula(
                aluno_id=aluno.id,
                data_inicio=data_dt,
                data_fim=data_fim_dt, 
                status="marcada",
                eh_reposicao=True,
                google_event_id=g_id, 
                lembrete_enviado=False
            )
            aluno.creditos_reposicao -= 1
            db.add(nova_aula)

        # --- CASO B: REAGENDAR EXISTENTE -
        else:
            aula = db.query(models.Aula).filter(
                models.Aula.id == aula_id, 
                models.Aula.aluno_id == aluno.id
            ).first()

            if not aula:
                return "Erro: Aula não encontrada."

            # Sincronização Google: Remove o antigo e cria o novo
            try:
                if aula.google_event_id:
                    remover_evento_google(aula.google_event_id)
                
                titulo = f"Aula: {aluno.nome} (Reagendada)"
                g_id = criar_evento(data_dt, data_fim_dt, titulo)
                aula.google_event_id = g_id
            except Exception as ge:
                print(f"⚠️ Erro Google Calendar (Update): {ge}")

            aula.data_inicio = data_dt
            aula.data_fim = data_fim_dt
            aula.status = "marcada"
            aula.lembrete_enviado = False

        db.commit()
        return RedirectResponse(url=f"/portal/{token}?sucesso=true", status_code=303)

    except Exception as e:
        db.rollback()
        print(f"❌ Erro: {e}")
        return f"Erro ao processar: {e}"