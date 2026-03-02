import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app.database import Base, get_db
from app.services import whatsapp

# 1. Configuração de um banco de dados SQLite em memória para testes
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Cria um banco de dados limpo para cada teste"""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """Cria um cliente de teste que usa o banco de dados de teste"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Substitui a dependência de banco real pela de teste
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def mock_whatsapp(monkeypatch):
    """Finge o envio de WhatsApp para que os testes não gastem créditos ou enviem SPAM"""
    mock = MagicMock()
    # Substitui a função real pela versão 'fake'
    monkeypatch.setattr(whatsapp, "enviar_whatsapp", mock)
    return mock