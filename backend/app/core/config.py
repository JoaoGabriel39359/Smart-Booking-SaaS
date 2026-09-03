import os
import secrets
from datetime import datetime
import pytz

SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TELEFONE_PROFESSOR = os.getenv("TELEFONE_PROFESSOR", "")
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

def agora_br() -> datetime:
    """Retorna o datetime atual no fuso horário de Brasília (UTC-3) sem tzinfo (naive)."""
    return datetime.now(pytz.timezone(TIMEZONE)).replace(tzinfo=None)
