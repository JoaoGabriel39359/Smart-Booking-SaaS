# Backend

A aplicação FastAPI fica em `backend/app`. Execute a partir da raiz do projeto:

```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Os arquivos `.env` e `requirements.txt` permanecem na raiz. Os testes ficam em
`backend/tests` e são descobertos a partir da raiz por meio do `pytest.ini`. O FastAPI
serve o build único localizado em `frontend/dist`.
