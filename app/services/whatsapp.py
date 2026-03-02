import requests

def enviar_whatsapp(numero, mensagem):
    # Configurações da sua Evolution API
    url = "https://sua-api.com/message/sendText/SuaInstancia"
    payload = {
        "number": f"55{numero}", # Garante o código do Brasil
        "text": mensagem
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": "SUA_CHAVE_API_AQUI"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    return response.json()