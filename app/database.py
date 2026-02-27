from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# URL para o Postgres Local
DB_URL = "postgresql://postgres:8899jgvb@localhost:5432/agenda_saas"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    # Importamos os modelos aqui para o Base saber que eles existem
    import models 
    
    print("Conectando ao banco e criando tabelas...")
    try:
        # Cria as tabelas Aluno, Aula, Conversa e Turma
        Base.metadata.create_all(bind=engine)
        print("Sucesso! O esquema do banco (Alunos, Aulas, Turmas, Conversas) foi sincronizado.")
    except Exception as e:
        print(f"Erro ao conectar ou criar tabelas: {e}")