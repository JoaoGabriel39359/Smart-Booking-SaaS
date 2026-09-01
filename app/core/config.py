import os
from datetime import datetime
import pytz

SECRET_KEY = os.getenv("SECRET_KEY", "zm50gNdO9resXqU2xxjsLiRgZKvAiWX561gVu4VHeEU")
BASE_URL = os.getenv("BASE_URL", "https://smart-booking-saas.onrender.com").rstrip("/")
TELEFONE_PROFESSOR = os.getenv("TELEFONE_PROFESSOR", "5522992011011")
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

def agora_br() -> datetime:
    """Retorna o datetime atual no fuso horário de Brasília (UTC-3) sem tzinfo (naive)."""
    return datetime.now(pytz.timezone(TIMEZONE)).replace(tzinfo=None)
