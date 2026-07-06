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
    # Tenta pegar das variáveis de ambiente (Render)
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if client_id and client_secret and refresh_token:
        # Se estiver no Render, monta as credenciais direto da memória
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
    else:
        # Se estiver no Localhost, tenta ler os arquivos (seu código antigo)
        BASE_DIR = os.getcwd()
        TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
        if os.path.exists(TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        else:
            raise Exception("Credenciais do Google não encontradas no Ambiente nem no token.json")

    # Atualiza o token se estiver expirado
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build('calendar', 'v3', credentials=creds)

# ==============================
# CRIAR EVENTO
# ==============================
def criar_evento(inicio: datetime, fim: datetime, nome_aluno: str, meet_link_existente: str = None):
    service = conectar_google()
    
    evento = {
        "summary": f"Aula - {nome_aluno}",
        "start": {"dateTime": inicio.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": fim.isoformat(), "timeZone": "America/Sao_Paulo"},
    }

    # Cenário A: O professor já passou um link existente (ou já geramos um antes)
    if meet_link_existente:
        evento["description"] = f"Link da aula: {meet_link_existente}"
        evento["location"] = meet_link_existente
        evento["conferenceData"] = {
            "entryPoints": [{"entryPointType": "video", "uri": meet_link_existente}],
            "conferenceSolution": {"key": {"type": "hangoutsMeet"}}
        }
        
        evento_criado = service.events().insert(
            calendarId="primary", 
            body=evento
        ).execute()
    
    # Cenário B: Não há link nenhum, pedimos para o Google gerar um do zero
    else:
        evento["conferenceData"] = {
            "createRequest": {
                "requestId": f"meet_{int(inicio.timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }
        
        # conferenceDataVersion=1 é obrigatório para o Google processar o 'createRequest'
        evento_criado = service.events().insert(
            calendarId="primary", 
            body=evento,
            conferenceDataVersion=1 
        ).execute()

    # Captura o link que o Google acabou de gerar, ou mantém o que já existia
    meet_link = evento_criado.get("hangoutLink") or meet_link_existente
    
    # Retorna o ID do Evento e o Link final do Meet
    return evento_criado["id"], meet_link

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