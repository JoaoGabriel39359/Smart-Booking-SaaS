from app.database import engine
from app.models import Base

# Isso vai apagar TODAS as tabelas e recriá-las com as colunas novas
print("Limpando banco de dados...")
Base.metadata.drop_all(bind=engine)
print("Recriando tabelas...")
Base.metadata.create_all(bind=engine)
print("Pronto! Agora pode rodar o uvicorn novamente.")