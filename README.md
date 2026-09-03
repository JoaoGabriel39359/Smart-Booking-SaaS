# One School — Agenda SaaS

Monólito para gestão de aulas, turmas, professores, frequência e reposições. O backend usa FastAPI/PostgreSQL e o painel usa React/TypeScript, mantendo o visual já conhecido do sistema One School.

## Estrutura

```text
agenda_saas/
├── backend/app/       # API FastAPI, regras, rotas e jobs
├── backend/tests/     # testes automatizados do backend
├── frontend/          # painel React + TypeScript + Vite
├── migrations/        # ajustes SQL para bancos já existentes
├── .env               # variáveis locais (não versionado)
├── .env.example       # modelo seguro de configuração
├── .gitignore
├── pytest.ini
└── requirements.txt
```

O FastAPI serve diretamente o build em `frontend/dist`. O frontend antigo foi removido.

## Configuração

Copie `.env.example` para `.env` e preencha os valores reais:

```env
DATABASE_URL=postgresql://usuario:senha@host:porta/database
ADMIN_USER=seu_usuario
ADMIN_PASS=sua_senha
SECRET_KEY=uma_chave_longa_e_aleatoria
BASE_URL=http://localhost:8000
TIMEZONE=America/Sao_Paulo
TELEFONE_PROFESSOR=5511999999999

GOOGLE_CLIENT_ID=seu_id
GOOGLE_CLIENT_SECRET=seu_secret
GOOGLE_REFRESH_TOKEN=seu_refresh_token

URL_WPP=http://host-da-evolution:8080
INSTANCIA_WPP=nome_da_instancia
TOKEN_WPP=seu_token
```

## Executar

Na raiz do projeto:

```bash
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Acesse `http://localhost:8000/login`.

## Testar

```bash
python -m pytest -q
cd frontend && npm run build
```

## Produção

Antes do primeiro deploy desta versão em um banco existente, execute o SQL de
`migrations/001_creditos_cancelamento.sql`. Depois configure as variáveis de ambiente,
gere o frontend e inicie o FastAPI com o mesmo comando acima.

### Render

O arquivo `render.yaml` mantém os comandos do deploy alinhados à estrutura do projeto.
Ao configurar um Web Service manualmente no painel do Render, deixe **Root Directory**
vazio e use:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
```

Serviços já criados manualmente não passam a usar o `render.yaml` automaticamente; nesse
caso, atualize o **Start Command** em Settings e solicite um novo deploy.

O diretório `frontend/dist` permanece no repositório para que o painel esteja disponível
mesmo em ambientes de deploy que executem apenas o processo Python. Sempre gere um novo
build após alterar arquivos em `frontend/src`.
