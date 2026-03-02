from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from datetime import datetime
from pathlib import Path
import os

SCOPES = ['https://www.googleapis.com/auth/calendar']

BASE_DIR = os.getcwd()
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

print(f"DEBUG: Procurando credenciais em: {CREDENTIALS_PATH}")
if not os.path.exists(CREDENTIALS_PATH):
    print("⚠️ AVISO: credentials.json NÃO ENCONTRADO!")

# ==============================
# CONEXÃO
# ==============================
def conectar_google():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

# ==============================
# CRIAR EVENTO
# ==============================
def criar_evento(inicio: datetime, fim: datetime, nome_aluno: str):
    service = conectar_google()
    evento = {
        "summary": f"Aula - {nome_aluno}",
        "start": {"dateTime": inicio.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": fim.isoformat(), "timeZone": "America/Sao_Paulo"},
    }
    evento_criado = service.events().insert(calendarId="primary", body=evento).execute()
    return evento_criado["id"]

# ==============================
# DELETAR EVENTO (remover_evento_google)
# ==============================
def remover_evento_google(event_id: str):
    """Deleta um evento do Google Calendar pelo ID"""
    try:
        service = conectar_google() # Aqui estava o erro: chamava 'obter_servico'
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception as e:
        print(f"Erro ao deletar evento no Google: {e}")
        return False

# Mantendo este apelido para não quebrar outros arquivos que usem o nome antigo
def deletar_evento(event_id: str):
    return remover_evento_google(event_id)

# ==============================
# LISTAR EVENTOS
# ==============================
def listar_eventos(inicio: datetime, fim: datetime):
    service = conectar_google()
    eventos = service.events().list(
        calendarId="primary",
        timeMin=inicio.isoformat() + "Z",
        timeMax=fim.isoformat() + "Z",
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return eventos.get("items", [])