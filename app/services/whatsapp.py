import requests
import os
import json

# Pegamos as configurações do ambiente (Render)
EVO_URL = os.getenv("URL_WPP")
EVO_KEY = os.getenv("TOKEN_WPP")
EVO_INSTANCE = os.getenv("INSTANCIA_WPP")

if not all([EVO_URL, EVO_KEY, EVO_INSTANCE]):
    print("⚠️ ERRO: Uma ou mais variáveis do WhatsApp não foram carregadas!")

def enviar_whatsapp(numero: str, mensagem: str):
    # 1. Limpa TUDO o que não for número
    numero_limpo = "".join(filter(str.isdigit, numero))

    # 2. Garante o prefixo 55 se for Brasil (números de 10 ou 11 dígitos)
    if len(numero_limpo) <= 11:
        if not numero_limpo.startswith("55"):
            numero_limpo = f"55{numero_limpo}"

    # 3. Consulta o JID oficial no WhatsApp para evitar o bug do "Aguardando mensagem" no iOS
    destinatario = numero_limpo
    try:
        url_check = f"{EVO_URL}/chat/whatsappNumbers/{EVO_INSTANCE}"
        headers_check = {
            "Content-Type": "application/json",
            "apikey": EVO_KEY
        }
        payload_check = {
            "numbers": [numero_limpo]
        }
        response_check = requests.post(url_check, headers=headers_check, json=payload_check, timeout=5)
        if response_check.status_code in [200, 201]:
            data = response_check.json()
            if isinstance(data, list) and len(data) > 0:
                contato = data[0]
                if contato.get("exists") and contato.get("jid"):
                    destinatario = contato.get("jid")
                    print(f"🔍 JID oficial resolvido para {numero_limpo} -> {destinatario}")
        else:
            print(f"⚠️ Erro ao consultar whatsappNumbers ({response_check.status_code}): {response_check.text}")
    except Exception as e:
        print(f"⚠️ Falha ao conectar ao whatsappNumbers da Evolution: {e}")
    
    # A URL deve ser EXATAMENTE essa para a v1.8.3
    url = f"{EVO_URL}/message/sendText/{EVO_INSTANCE}"

    headers = {
        "Content-Type": "application/json",
        "apikey": EVO_KEY # Aqui vai o token do Render
    }

    payload = {
        "number": destinatario, # Agora usamos o JID ou número exato verificado
        "options": {
            "delay": 1200,
            "presence": "composing"
        },
        "textMessage": {
            "text": mensagem
        }
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"✅ WhatsApp enviado com sucesso para {numero_limpo}")
            return True
        else:
            print(f"❌ Erro Evolution ({response.status_code}): {response.text}")
            return False
            
    except Exception as e:
        print(f"⚠️ Falha crítica ao conectar na VPS da Evolution: {e}")
        return False