# 📅 SaaS de Agenda Online com IA e Automação de WhatsApp

Este é um sistema robusto de agendamento (SaaS) desenvolvido com **FastAPI** e **PostgreSQL**, focado em automação de regras de negócio para planos VIP, gestão de créditos de reposição e notificações inteligentes via **WhatsApp (Twilio)**.

## 🚀 Funcionalidades Principais

* **Agendamento Inteligente**: Integração com **Google Calendar API** para sincronização de horários.
* **Regras de Negócio VIP**: 
    * Geração automática de créditos de reposição apenas para cancelamentos feitos com mais de 2h de antecedência.
    * Controle de validade de créditos (15 ou 30 dias).
* **Portal do Aluno Responsivo**: Interface mobile-first (Tailwind CSS) para reagendamento simplificado.
* **Automações de WhatsApp (Cron Jobs)**:
    * **Lembrete de Vencimento**: Avisos automáticos 15 dias e 1 dia antes de um crédito expirar.
    * **Confirmação 24h**: Mensagem para alunos VIP confirmarem ou reagendarem a aula de amanhã.
    * **Lembrete "In-Time"**: Notificação enviada 20 minutos antes do início da aula.
* **Logs e Segurança**: Sistema de logs para controle de envio de notificações e status de aulas.

## 🛠️ Tecnologias Utilizadas

* **Backend**: Python 3.10+ com [FastAPI](https://fastapi.tiangolo.com/)
* **Banco de Dados**: PostgreSQL (SQLAlchemy ORM)
* **Mensageria**: [Twilio API](https://www.twilio.com/) para WhatsApp
* **Frontend**: HTML5, Tailwind CSS e Jinja2 Templates
* **Integração**: Google Calendar API v3
* **Túnel**: [Ngrok](https://ngrok.com/) para testes de Webhooks locais

## 📋 Pré-requisitos

* Python instalado
* PostgreSQL rodando
* Conta no Twilio (Sandbox habilitado)
* Credenciais do Google Cloud Console (`credentials.json`)

## 🔧 Instalação e Configuração

1. **Clone o repositório**:
   ```bash
   git clone [https://github.com/seu-usuario/agenda-saas.git](https://github.com/seu-usuario/agenda-saas.git)
   cd agenda-saas