from twilio.rest import Client
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def enviar_whatsapp(numero: str, mensagem: str):
    # Remove espaços ou traços que possam vir do banco
    numero_limpo = "".join(filter(str.isdigit, numero))
    
    # Se o número não começar com 55, a gente adiciona
    if not numero_limpo.startswith("55"):
        numero_limpo = f"55{numero_limpo}"

    try:
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=mensagem,
            to=f"whatsapp:+{numero_limpo}" # O '+' é importante para o Twilio
        )
        return message.sid
    except Exception as e:
        print(f"Erro detalhado no Twilio: {e}")
        raise e

def enviar_boas_vindas_whatsapp(nome_aluno, nome_turma, telefone):
    mensagem = (
        f"Olá {nome_aluno}! 👋\n\n"
        f"Seja muito bem-vindo(a) à nossa escola. ✅\n"
        f"Sua matrícula na turma *{nome_turma}* foi confirmada com sucesso!\n\n"
        f"Estamos ansiosos para começar as aulas com você."
    )
    
    # Agora chamamos a função de envio real do Twilio
    try:
        sid = enviar_whatsapp(telefone, mensagem)
        print(f"WhatsApp enviado com sucesso! SID: {sid}")
        return True
    except Exception as e:
        print(f"Falha técnica ao enviar pelo Twilio: {e}")
        return False