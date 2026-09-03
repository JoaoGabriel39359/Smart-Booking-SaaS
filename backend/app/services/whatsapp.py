import os

import requests

EVO_URL = os.getenv("URL_WPP")
EVO_KEY = os.getenv("TOKEN_WPP")
EVO_INSTANCE = os.getenv("INSTANCIA_WPP")


def _configuracao_pronta() -> bool:
    return bool(EVO_URL and EVO_KEY and EVO_INSTANCE)


def _resumo_resposta(response: requests.Response) -> str:
    return (response.text or "sem detalhes")[:500]


def enviar_whatsapp(numero: str, mensagem: str) -> bool:
    """Envia uma mensagem e só retorna True quando a Evolution confirma o envio."""
    if not _configuracao_pronta():
        print("❌ WhatsApp não configurado: confira URL_WPP, TOKEN_WPP e INSTANCIA_WPP.")
        return False

    numero_limpo = "".join(filter(str.isdigit, numero or ""))
    if not numero_limpo:
        print("❌ WhatsApp não enviado: telefone do destinatário está vazio.")
        return False
    if len(numero_limpo) <= 11 and not numero_limpo.startswith("55"):
        numero_limpo = f"55{numero_limpo}"

    base_url = str(EVO_URL).rstrip("/")
    headers = {"Content-Type": "application/json", "apikey": str(EVO_KEY)}
    destinatario = numero_limpo

    try:
        response_check = requests.post(
            f"{base_url}/chat/whatsappNumbers/{EVO_INSTANCE}",
            headers=headers,
            json={"numbers": [numero_limpo]},
            timeout=5,
        )
        if response_check.status_code in (200, 201):
            data = response_check.json()
            if isinstance(data, list) and data:
                contato = data[0]
                if contato.get("exists") and contato.get("jid"):
                    destinatario = contato["jid"]
        else:
            detalhe = _resumo_resposta(response_check)
            print(f"⚠️ Evolution recusou a consulta do número ({response_check.status_code}): {detalhe}")
            if response_check.status_code == 404 and "does not exist" in detalhe.lower():
                print("❌ A INSTANCIA_WPP configurada não existe nesta Evolution API.")
                return False
    except requests.RequestException as exc:
        print(f"⚠️ Não foi possível consultar o número na Evolution: {exc}")

    payload = {
        "number": destinatario,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": mensagem},
    }

    try:
        response = requests.post(
            f"{base_url}/message/sendText/{EVO_INSTANCE}",
            headers=headers,
            json=payload,
            timeout=12,
        )
        if response.status_code in (200, 201):
            print(f"✅ WhatsApp enviado com sucesso para {numero_limpo}")
            return True
        print(f"❌ Evolution recusou o envio ({response.status_code}): {_resumo_resposta(response)}")
    except requests.RequestException as exc:
        print(f"❌ Falha ao conectar à Evolution API: {exc}")
    return False
