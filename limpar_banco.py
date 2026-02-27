from app.database import engine
from app.models import Base

print("Limpando tabelas...")
Base.metadata.drop_all(bind=engine)
print("Recriando tabelas com a estrutura nova (incluindo turma_id)...")
Base.metadata.create_all(bind=engine)
print("Pronto! Agora você pode rodar o uvicorn novamente.")