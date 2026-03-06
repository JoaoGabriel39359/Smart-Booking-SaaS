import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer 

# --- CONFIGURAÇÕES DE SEGURANÇA JWT ---
SECRET_KEY = "zm50gNdO9resXqU2xxjsLiRgZKvAiWX561gVu4VHeEU" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- LÓGICA JWT ---
def criar_token_acesso(dados: dict):
    para_codificar = dados.copy()
    expiracao = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    para_codificar.update({"exp": expiracao})
    return jwt.encode(para_codificar, SECRET_KEY, algorithm=ALGORITHM)

def verificar_token(token: str = Depends(oauth2_scheme)):
    try:
        # Tenta decodificar o crachá usando sua chave secreta
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario = payload.get("sub")
        if usuario is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return usuario # Retorna o nome do usuário se estiver tudo ok
    except JWTError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")