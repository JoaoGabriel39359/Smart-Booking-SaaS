import os
import pytz
from dotenv import load_dotenv
load_dotenv()
from app.services.whatsapp import enviar_whatsapp
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

# Importações do seu projeto
from app.services.google_calendar import criar_evento, remover_evento_google
from app.routes import alunos, aulas, webhook, turmas 
from app.database import Base, engine, get_db
from app import models
from app.services.lembretes import verificar_lembretes_background
from app.services.gerar_agenda import gerar_aulas_da_semana
from app.auth import criar_token_acesso, pwd_context

# --- LÓGICA DE CAMINHOS ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_PATH = os.path.join(CURRENT_DIR, "static")
TEMPLATES_PATH = os.path.join(CURRENT_DIR, "templates")
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
FRONTEND_PATH = os.path.join(BASE_DIR, "frontend")
ADMIN_USER = os.getenv("ADMIN_USER", "OneLanguage")
ADMIN_PASS_RAW = os.getenv("ADMIN_PASS", "8899jgvb")
SENHA_MESTRA_HASH = pwd_context.hash(ADMIN_PASS_RAW)

# --- AGENDADOR (SCHEDULER) ---
# Definimos aqui antes do lifespan para evitar erro de "não definido"
scheduler = BackgroundScheduler()
scheduler.add_job(verificar_lembretes_background, 'interval', minutes=1)
scheduler.add_job(gerar_aulas_da_semana, 'cron', day_of_week='mon', hour=0, minute=0)

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Sistema Agenda SaaS Iniciado")
    if not scheduler.running:
        scheduler.start()
    # Cria as tabelas ao iniciar
    Base.metadata.create_all(bind=engine)
    yield
    print("🛑 Sistema Encerrado")
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(title="Agenda SaaS", lifespan=lifespan)

# --- MIDDLEWARE / STATIC ---
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
app.mount("/frontend", StaticFiles(directory=os.path.abspath(FRONTEND_PATH)), name="frontend")
templates = Jinja2Templates(directory=TEMPLATES_PATH)

# --- ROTAS ---
app.include_router(turmas.router)
app.include_router(alunos.router)
app.include_router(aulas.router)
app.include_router(webhook.router)

@app.post("/token")
async def login(dados: dict):
    
    username = dados.get("username")
    password = dados.get("password")

    # Verificamos se o usuário bate e se a senha confere com o hash fixo
    if username != ADMIN_USER or not pwd_context.verify(password, SENHA_MESTRA_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Credenciais inválidas"
        )

    # Se passou, gera o token
    token = criar_token_acesso(dados={"sub": ADMIN_USER})
    return {"access_token": token, "token_type": "bearer"}

# --- ROTAS DE PÁGINAS ---

@app.get("/")
def home():
    return {"status": "SaaS de Agenda Online Rodando"}

# Painel do Professor corrigido com caminho absoluto
@app.get("/painel")
async def painel():
    caminho_index = os.path.join(BASE_DIR, "frontend", "index.html")
    
    # Se o arquivo não existir, o Render vai nos dizer EXATAMENTE onde ele procurou
    if not os.path.exists(caminho_index):
        # Lista os arquivos da raiz para a gente ver o que tem lá
        arquivos_na_raiz = os.listdir(BASE_DIR)
        return {
            "erro": "Arquivo não encontrado",
            "onde_procurei": caminho_index,
            "arquivos_que_existem_na_raiz": arquivos_na_raiz
        }
    
    return FileResponse(caminho_index)

# ... (restante do código do portal e reagendamento continua igual)

# NOVO PORTAL DO ALUNO (Unificado: Ver, Cancelar e Agendar)
@app.get("/portal/{token}", response_class=HTMLResponse)
async def pagina_portal_aluno(token: str, request: Request, db: Session = Depends(get_db)):
    # 1. Ajuste de Fuso Horário
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora_br = datetime.now(fuso_br).replace(tzinfo=None)

    aluno = db.query(models.Aluno).filter(models.Aluno.token_acesso == token).first()
    
    if not aluno:
        return HTMLResponse(content="Link de acesso inválido ou expirado.", status_code=404)

    # 2. LOG DE DEBUG (Isso vai aparecer no seu painel do Render)
    # Vamos dar uma margem de 6 horas para garantir que apareça QUALQUER aula de hoje
    filtro_hora = agora_br - timedelta(hours=6)
    print(f"--- DEBUG PORTAL ---")
    print(f"Agora no Brasil: {agora_br}")
    print(f"Buscando aulas após: {filtro_hora}")

    # 3. Busca das aulas
    aulas_aluno = db.query(models.Aula).filter(
        models.Aula.aluno_id == aluno.id,
        models.Aula.status == "marcada",
        models.Aula.data_inicio >= filtro_hora
    ).order_by(models.Aula.data_inicio).all()

    # Log para ver se o banco retornou algo
    print(f"Aulas encontradas no banco: {len(aulas_aluno)}")
    for a in aulas_aluno:
        print(f"ID: {a.id} | Data: {a.data_inicio} | Status: {a.status}")
    print(f"--------------------")

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
        # 1. Conversão de Data Robusta
        # Aceita formatos ISO (T) e formatos com espaço, com ou sem segundos
        try:
            nova_data_limpa = nova_data.replace("T", " ")
            if len(nova_data_limpa) == 16:  # Formato YYYY-MM-DD HH:MM
                data_dt = datetime.strptime(nova_data_limpa, "%Y-%m-%d %H:%M")
            else:  # Formato com segundos ou ISO completo
                data_dt = datetime.fromisoformat(nova_data.replace("Z", ""))
        except Exception as e:
            print(f"❌ Erro na conversão de data: {nova_data} -> {e}")
            return f"Erro no formato da data enviada: {nova_data}"

        data_fim_dt = data_dt + timedelta(hours=1)

        if aula_id == 0:
            if aluno.creditos_reposicao <= 0:
                return HTMLResponse(content="Erro: Você não possui créditos de reposição.", status_code=400)
            
            g_id = None
            try:
                titulo = f"Reposição: {aluno.nome}"
                g_id = criar_evento(data_dt, data_fim_dt, titulo)
            except Exception as ge:
                print(f"⚠️ Erro Google Calendar: {ge}")

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

        # --- CASO B: REAGENDAR EXISTENTE ---
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
        try:
            link_portal = f"https://smart-booking-saas.onrender.com/portal/{token}"
            msg_reagendado = (
                f"Tudo certo, {aluno.nome}! ✅\n"
                f"Sua aula foi remarcada para: *{data_dt.strftime('%d/%m às %H:%M')}*.\n\n"
                f"Veja seus horários no portal:\n{link_portal}"
            )
            enviar_whatsapp(aluno.telefone, msg_reagendado)
        except Exception as e:
            print(f"Erro ao avisar reagendamento: {e}")
        # ---------------------------------------------

        return RedirectResponse(url=f"/portal/{token}?sucesso=true", status_code=303)

    except Exception as e:
        db.rollback()
        print(f"❌ Erro no servidor: {e}")
        # Retornar como HTMLResponse garante que o erro apareça de forma legível no navegador
        return HTMLResponse(content=f"Erro ao processar agendamento: {str(e)}", status_code=500)
