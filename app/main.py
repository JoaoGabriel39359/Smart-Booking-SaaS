from fastapi import FastAPI, Request, Depends, Form
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

    # Mantemos sua lógica de contexto para o template
    contexto_aluno = {
        "id": aluno.id,
        "nome": aluno.nome,
        "sobrenome": aluno.sobrenome,
        "telefone": aluno.telefone,
        "email": aluno.email,
        "token": aluno.token_acesso, # Adicionamos o token aqui para usar nos formulários se necessário
        "tipo": aluno.tipo.name if hasattr(aluno.tipo, 'name') else str(aluno.tipo),
        "creditos_reposicao": aluno.creditos_reposicao
    }

    return templates.TemplateResponse("portal.html", {
        "request": request,
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
                data_fim=data_fim_dt, # Adicionado fim da aula
                status="marcada",
                eh_reposicao=True,
                google_event_id=g_id, # Salva o ID do Google
                lembrete_enviado=False
            )
            aluno.creditos_reposicao -= 1
            db.add(nova_aula)

        # --- CASO B: REAGENDAR EXISTENTE (Remover antigo e Criar novo) ---
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