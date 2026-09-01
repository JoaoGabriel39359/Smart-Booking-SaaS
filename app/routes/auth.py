import os
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.auth import criar_token_acesso, pwd_context

router = APIRouter(tags=["autenticacao"])

templates = Jinja2Templates(directory="app/frontend/templates")

@router.get("/login", response_class=HTMLResponse)
async def exibir_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS_RAW = os.getenv("ADMIN_PASS")
SENHA_MESTRA_HASH = pwd_context.hash(ADMIN_PASS_RAW) if ADMIN_PASS_RAW else ""


@router.post("/token")
async def login(dados: dict):
    username = dados.get("username")
    password = dados.get("password")

    if not ADMIN_USER or not ADMIN_PASS_RAW:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credenciais de administrador não configuradas no ambiente."
        )

    # Verificamos se o usuário bate e se a senha confere com o hash fixo
    if username != ADMIN_USER or not pwd_context.verify(password, SENHA_MESTRA_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Credenciais inválidas"
        )

    # Se passou, gera o token
    token = criar_token_acesso(dados={"sub": ADMIN_USER})
    return {"access_token": token, "token_type": "bearer"}
