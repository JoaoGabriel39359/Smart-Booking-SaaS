# 📅 OneLanguage SaaS - Agenda Inteligente & Automação

Este é um sistema **SaaS (Software as a Service)** de alto nível para gestão de agendas, desenvolvido com **FastAPI** e **PostgreSQL**. O foco do projeto é automatizar a rotina de professores e escolas, integrando diretamente com o **Google Calendar** e disparando notificações estratégicas via **WhatsApp (Evolution API)**.

---

## 🚀 Funcionalidades Principais

* **Sincronização com Google Calendar**: Integração total com a API v3 do Google para gestão de horários e disponibilidade em tempo real.
* **Gestão de Planos VIP & Turmas**: 
    * Regras automáticas para créditos de reposição (apenas para cancelamentos com > 3h de antecedência).
    * Diferenciação de tratamento entre alunos VIP e turmas regulares.
* **Notificações Inteligentes via WhatsApp**:
    * **Lembrete de Aula (20 min antes)**: Disparo automático para garantir a pontualidade.
    * **Confirmação Estratégica (10h antes)**: Exclusivo para alunos VIP, facilitando o reagendamento antecipado.
    * **Avisos de Expiração**: Alertas automáticos sobre a validade de créditos (15 ou 30 dias).
* **Portal do Aluno Responsivo**: Interface *mobile-first* construída com **Tailwind CSS**, permitindo que o aluno gerencie suas aulas de qualquer lugar.

---

## 🛠️ Tecnologias Utilizadas

| Camada | Tecnologia |
| :--- | :--- |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) |
| **Banco de Dados** | PostgreSQL + SQLAlchemy (Hospedado via Supabase) |
| **WhatsApp** | [Evolution API](https://evolution-api.com/) |
| **Calendário** | Google Calendar API v3 (OAuth2) |
| **Frontend** | Jinja2 Templates & Tailwind CSS |
| **Deploy** | Render |

---

## 📋 Arquitetura de Integração

O sistema utiliza um fluxo de autenticação robusto para garantir que as aulas sejam marcadas diretamente na agenda do professor:

1.  **OAuth2 Flow**: O professor autoriza o app uma única vez através do Google.
2.  **Refresh Token**: O sistema armazena o token de atualização para manter o acesso vitalício.
3.  **Background Tasks**: Jobs assíncronos verificam o banco de dados e disparam lembretes via WhatsApp de forma não-bloqueante.

---

## 🔧 Configuração do Ambiente

Crie um arquivo `.env` na raiz do projeto e preencha conforme o exemplo abaixo:

```env
# GOOGLE CALENDAR
GOOGLE_CLIENT_ID=seu_id_aqui
GOOGLE_CLIENT_SECRET=seu_secret_aqui
GOOGLE_REFRESH_TOKEN=seu_refresh_token_aqui

# WHATSAPP (EVOLUTION API)
URL_WPP=http://seu-ip-da-api:8080
INSTANCIA_WPP=Nome_da_Instancia
TOKEN_WPP=seu_token_da_api

# BANCO DE DADOS
DATABASE_URL=postgresql://usuario:senha@host:porta/database

🏗️ Como Executar
Instale as dependências:

Bash
pip install -r requirements.txt
Gere o Token de Acesso (Primeira vez):
O sistema conta com um script auxiliar para gerar o token.json inicial do professor.

Bash: 
python gerar_token.py
Inicie o Servidor:

Bash: 
uvicorn app.main:app --host 0.0.0.0 --port 8000