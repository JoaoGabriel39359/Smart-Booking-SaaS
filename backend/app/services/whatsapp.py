import os
from dataclasses import dataclass
from typing import Iterable, Optional

import requests


@dataclass(frozen=True)
class ResultadoEnvio:
    aceito: bool
    provider: str
    status: str
    id_mensagem: Optional[str] = None
    wamid: Optional[str] = None
    erro_codigo: Optional[str] = None
    erro_mensagem: Optional[str] = None

    def __bool__(self) -> bool:
        return self.aceito


def normalizar_telefone(numero: str, incluir_mais: bool = False) -> str:
    numero_limpo = "".join(filter(str.isdigit, numero or ""))
    if len(numero_limpo) <= 11 and not numero_limpo.startswith("55"):
        numero_limpo = f"55{numero_limpo}"
    if incluir_mais and numero_limpo:
        return f"+{numero_limpo}"
    return numero_limpo


def provedor_whatsapp() -> str:
    configurado = os.getenv("WHATSAPP_PROVIDER", "").strip().lower()
    if configurado:
        return configurado if configurado in {"ycloud", "evolution", "disabled"} else "disabled"
    if os.getenv("YCLOUD_API_KEY") and os.getenv("YCLOUD_PHONE_NUMBER"):
        return "ycloud"
    if os.getenv("URL_WPP") and os.getenv("TOKEN_WPP") and os.getenv("INSTANCIA_WPP"):
        return "evolution"
    return "disabled"


def configuracao_whatsapp_publica() -> dict:
    provider = provedor_whatsapp()
    if provider == "ycloud":
        pronto = bool(os.getenv("YCLOUD_API_KEY") and os.getenv("YCLOUD_PHONE_NUMBER"))
    elif provider == "evolution":
        pronto = bool(os.getenv("URL_WPP") and os.getenv("TOKEN_WPP") and os.getenv("INSTANCIA_WPP"))
    else:
        pronto = False
    return {"provider": provider, "configurado": pronto}


def _resumo_resposta(response: requests.Response) -> str:
    return (response.text or "sem detalhes")[:500]


def _resultado_erro(provider: str, status: str, codigo: str, mensagem: str) -> ResultadoEnvio:
    return ResultadoEnvio(
        aceito=False,
        provider=provider,
        status=status,
        erro_codigo=codigo,
        erro_mensagem=mensagem[:1000],
    )


def _enviar_ycloud(
    numero: str,
    *,
    mensagem: Optional[str] = None,
    template_nome: Optional[str] = None,
    template_idioma: str = "pt_BR",
    parametros: Optional[Iterable[str]] = None,
    external_id: Optional[str] = None,
) -> ResultadoEnvio:
    api_key = os.getenv("YCLOUD_API_KEY", "").strip()
    remetente = normalizar_telefone(os.getenv("YCLOUD_PHONE_NUMBER", ""), incluir_mais=True)
    if not api_key or not remetente:
        return _resultado_erro(
            "ycloud", "falhou", "CONFIGURACAO_AUSENTE",
            "Confira YCLOUD_API_KEY e YCLOUD_PHONE_NUMBER.",
        )

    destinatario = normalizar_telefone(numero, incluir_mais=True)
    if not destinatario:
        return _resultado_erro("ycloud", "falhou", "TELEFONE_VAZIO", "Telefone do destinatário vazio.")

    payload = {
        "from": remetente,
        "to": destinatario,
        "filterUnsubscribed": True,
        "filterBlocked": True,
    }
    if external_id:
        payload["externalId"] = external_id

    if template_nome:
        template = {
            "name": template_nome,
            "language": {"code": template_idioma, "policy": "deterministic"},
        }
        valores = [str(valor) for valor in (parametros or [])]
        if valores:
            template["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": valor} for valor in valores],
            }]
        payload.update({"type": "template", "template": template})
    elif mensagem:
        payload.update({"type": "text", "text": {"body": mensagem, "preview_url": True}})
    else:
        return _resultado_erro("ycloud", "falhou", "CONTEUDO_VAZIO", "Mensagem ou template não informado.")

    base_url = os.getenv("YCLOUD_API_URL", "https://api.ycloud.com/v2").rstrip("/")
    try:
        response = requests.post(
            f"{base_url}/whatsapp/messages",
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            json=payload,
            timeout=(5, 20),
        )
    except requests.RequestException as exc:
        # A falha pode acontecer depois de a API aceitar o pedido. Não repetimos
        # automaticamente uma situação ambígua, evitando mensagens duplicadas.
        return _resultado_erro("ycloud", "desconhecido", "ERRO_DE_REDE", str(exc))

    if response.status_code not in (200, 201, 202):
        return _resultado_erro(
            "ycloud", "falhou", str(response.status_code), _resumo_resposta(response)
        )

    try:
        data = response.json()
    except ValueError:
        return _resultado_erro(
            "ycloud", "desconhecido", "RESPOSTA_INVALIDA",
            "A YCloud retornou uma resposta sem JSON válido.",
        )

    if not isinstance(data, dict):
        return _resultado_erro(
            "ycloud", "desconhecido", "RESPOSTA_INVALIDA",
            "A YCloud retornou um JSON em formato inesperado.",
        )

    status = str(data.get("status") or "accepted").lower()
    if status not in {"accepted", "sent", "delivered", "read"}:
        return _resultado_erro(
            "ycloud", "falhou", str(data.get("errorCode") or status),
            str(data.get("errorMessage") or "A YCloud não aceitou a mensagem."),
        )
    return ResultadoEnvio(
        aceito=True,
        provider="ycloud",
        status=status,
        id_mensagem=str(data.get("id")) if data.get("id") else None,
        wamid=str(data.get("wamid")) if data.get("wamid") else None,
    )


def _enviar_evolution(numero: str, mensagem: str) -> ResultadoEnvio:
    evo_url = os.getenv("URL_WPP")
    evo_key = os.getenv("TOKEN_WPP")
    evo_instance = os.getenv("INSTANCIA_WPP")
    if not (evo_url and evo_key and evo_instance):
        return _resultado_erro(
            "evolution", "falhou", "CONFIGURACAO_AUSENTE",
            "Confira URL_WPP, TOKEN_WPP e INSTANCIA_WPP.",
        )

    numero_limpo = normalizar_telefone(numero)
    if not numero_limpo:
        return _resultado_erro("evolution", "falhou", "TELEFONE_VAZIO", "Telefone vazio.")

    base_url = str(evo_url).rstrip("/")
    headers = {"Content-Type": "application/json", "apikey": str(evo_key)}
    destinatario = numero_limpo
    try:
        response_check = requests.post(
            f"{base_url}/chat/whatsappNumbers/{evo_instance}",
            headers=headers,
            json={"numbers": [numero_limpo]},
            timeout=5,
        )
        if response_check.status_code in (200, 201):
            data = response_check.json()
            if isinstance(data, list) and data and data[0].get("exists") and data[0].get("jid"):
                destinatario = data[0]["jid"]
        elif response_check.status_code == 404 and "does not exist" in _resumo_resposta(response_check).lower():
            return _resultado_erro(
                "evolution", "falhou", "INSTANCIA_INEXISTENTE",
                "A INSTANCIA_WPP configurada não existe.",
            )
    except (requests.RequestException, ValueError, TypeError):
        pass

    payload = {
        "number": destinatario,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": mensagem},
    }
    try:
        response = requests.post(
            f"{base_url}/message/sendText/{evo_instance}",
            headers=headers,
            json=payload,
            timeout=12,
        )
    except requests.RequestException as exc:
        return _resultado_erro("evolution", "desconhecido", "ERRO_DE_REDE", str(exc))

    if response.status_code not in (200, 201):
        return _resultado_erro(
            "evolution", "falhou", str(response.status_code), _resumo_resposta(response)
        )
    try:
        data = response.json()
    except ValueError:
        data = {}
    chave = data.get("key") if isinstance(data, dict) else None
    message_id = chave.get("id") if isinstance(chave, dict) else None
    return ResultadoEnvio(
        aceito=True,
        provider="evolution",
        status="accepted",
        id_mensagem=str(message_id) if message_id else None,
    )


def enviar_whatsapp_detalhado(
    numero: str,
    mensagem: str,
    *,
    external_id: Optional[str] = None,
) -> ResultadoEnvio:
    """Envia texto livre. Na YCloud, use apenas dentro da janela de atendimento."""
    provider = provedor_whatsapp()
    if provider == "ycloud":
        return _enviar_ycloud(numero, mensagem=mensagem, external_id=external_id)
    if provider == "evolution":
        return _enviar_evolution(numero, mensagem)
    return _resultado_erro(
        "disabled", "falhou", "WHATSAPP_DESATIVADO",
        "Defina WHATSAPP_PROVIDER e as credenciais do provedor.",
    )


def enviar_template_whatsapp(
    numero: str,
    template_nome: str,
    parametros: Iterable[str],
    *,
    template_idioma: str = "pt_BR",
    external_id: Optional[str] = None,
    mensagem_fallback: str = "",
) -> ResultadoEnvio:
    provider = provedor_whatsapp()
    if provider == "ycloud":
        return _enviar_ycloud(
            numero,
            template_nome=template_nome,
            template_idioma=template_idioma,
            parametros=parametros,
            external_id=external_id,
        )
    if provider == "evolution":
        if not mensagem_fallback:
            return _resultado_erro(
                "evolution", "falhou", "FALLBACK_AUSENTE",
                "O texto de fallback da Evolution não foi informado.",
            )
        return _enviar_evolution(numero, mensagem_fallback)
    return _resultado_erro(
        "disabled", "falhou", "WHATSAPP_DESATIVADO",
        "Defina WHATSAPP_PROVIDER e as credenciais do provedor.",
    )


def enviar_whatsapp(numero: str, mensagem: str) -> bool:
    """Compatibilidade com respostas livres já existentes."""
    resultado = enviar_whatsapp_detalhado(numero, mensagem)
    if not resultado:
        print(
            f"❌ WhatsApp ({resultado.provider}) não aceitou a mensagem: "
            f"{resultado.erro_codigo} - {resultado.erro_mensagem}"
        )
    return bool(resultado)
