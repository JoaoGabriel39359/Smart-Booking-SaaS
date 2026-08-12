from sqlalchemy import create_engine
import os
from sqlalchemy.orm import sessionmaker, declarative_base

DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    # Fallback seguro para desenvolvimento local SQLite caso DATABASE_URL não esteja definida
    DB_URL = "sqlite:///./agenda_saas.db"
elif DB_URL.startswith("postgres://"):
    # Correção: Render/Supabase podem fornecer postgres:// mas SQLAlchemy exige postgresql://
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    from app import models 
    
    print("Conectando ao banco e criando tabelas...")
    try:
        Base.metadata.create_all(bind=engine)
        print("Sucesso! O esquema do banco (Alunos, Aulas, Turmas, Conversas) foi sincronizado.")
    except Exception as e:
        print(f"Erro ao conectar ou criar tabelas: {e}")