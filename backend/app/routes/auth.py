from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from app.auth import criar_token_acesso, pwd_context
from app.core.config import ADMIN_PASS, ADMIN_USER
from app.core.paths import FRONTEND_INDEX

router = APIRouter(tags=["autenticacao"])

@router.get("/login", response_class=HTMLResponse)
async def exibir_login():
    if not FRONTEND_INDEX.is_file():
        return HTMLResponse("Frontend não encontrado.", status_code=404)
    return FileResponse(FRONTEND_INDEX)

SENHA_MESTRA_HASH = pwd_context.hash(ADMIN_PASS) if ADMIN_PASS else ""


@router.post("/token")
async def login(dados: dict):
    username = dados.get("username")
    password = dados.get("password")

    if not ADMIN_USER or not ADMIN_PASS:
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
