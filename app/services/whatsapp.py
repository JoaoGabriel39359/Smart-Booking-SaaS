import requests
import os
import json

# Pegamos as configurações do ambiente (Render)
EVO_URL = os.getenv("EVOLUTION_URL")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
EVO_INSTANCE = os.getenv("EVOLUTION_INSTANCE")

def enviar_whatsapp(numero: str, mensagem: str):
    """
    Envia uma mensagem via Evolution API hospedada na VPS.
    """
    # 1. Remove espaços, parênteses e traços, mas MANTÉM o "+" se existir
    # Exemplo: "+1 (555) 123-4567" -> "+15551234567"
    numero_limpo = "".join(filter(lambda x: x.isdigit() or x == "+", numero))

    # 2. Lógica de Prefixo Internacional
    if not numero_limpo.startswith("+"):
        # Se não tem o "+", verificamos se o usuário já digitou o 55
        if not numero_limpo.startswith("55") and len(numero_limpo) <= 11:
            # Se tem 11 dígitos ou menos e não começa com 55, assumimos Brasil
            numero_limpo = f"55{numero_limpo}"
    else:
        # Se já tem o "+", removemos apenas o símbolo para a Evolution API processar
        numero_limpo = numero_limpo.replace("+", "")

    # 2. Montagem da URL da sua VPS
    url = f"{EVO_URL}/message/sendText/{EVO_INSTANCE}"

    # 3. Cabeçalhos de segurança
    headers = {
        "Content-Type": "application/json",
        "apikey": EVO_KEY
    }

    # 4. Corpo da mensagem (O que a Evolution espera)
    payload = {
        "number": numero_limpo,
        "options": {
            "delay": 1200, # Pequeno delay de 1.2s para parecer humano
            "presence": "composing" # Mostra "digitando..." no zap do aluno
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