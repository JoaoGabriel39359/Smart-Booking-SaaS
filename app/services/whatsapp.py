import requests
import os
import json

# Pegamos as configurações do ambiente (Render)
EVO_URL = os.getenv("EVOLUTION_URL")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
EVO_INSTANCE = os.getenv("EVOLUTION_INSTANCE")

def enviar_whatsapp(numero: str, mensagem: str):
    # 1. Limpa TUDO o que não for número
    numero_limpo = "".join(filter(str.isdigit, numero))

    # 2. Garante o prefixo 55 se for Brasil (números de 10 ou 11 dígitos)
    if len(numero_limpo) <= 11:
        if not numero_limpo.startswith("55"):
            numero_limpo = f"55{numero_limpo}"
    
    # A URL deve ser EXATAMENTE essa para a v1.8.3
    url = f"{EVO_URL}/message/sendText/{EVO_INSTANCE}"

    headers = {
        "Content-Type": "application/json",
        "apikey": EVO_KEY # Aqui vai o 8899jgvb que está no seu Render
    }

    payload = {
        "number": numero_limpo, # A Evolution v1 cuida do @s.whatsapp.net sozinha
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