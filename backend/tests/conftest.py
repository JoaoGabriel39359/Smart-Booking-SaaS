import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app.database import Base, get_db
from app.services import whatsapp

# 1. Configuração de um banco de dados SQLite em memória para testes
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
    c = TestClient(app)
    yield c
    c.close()
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def mock_whatsapp(monkeypatch):
    """Finge o envio de WhatsApp para que os testes não gastem créditos ou enviem SPAM"""
    mock = MagicMock()
    # Substitui a função real no local de definição
    monkeypatch.setattr(whatsapp, "enviar_whatsapp", mock)
    # E também nos locais onde foi importada diretamente para os namespaces dos módulos
    import app.routes.aulas
    import app.routes.alunos
    import app.routes.portal
    import app.services.lembretes
    monkeypatch.setattr(app.routes.aulas, "enviar_whatsapp", mock)
    monkeypatch.setattr(app.routes.alunos, "enviar_whatsapp", mock)
    monkeypatch.setattr(app.routes.portal, "enviar_whatsapp", mock)
    monkeypatch.setattr(app.services.lembretes, "enviar_whatsapp", mock)
    return mock


@pytest.fixture(autouse=True)
def mock_google_calendar(monkeypatch):
    """Impede que a suíte faça chamadas reais ao Google Calendar."""
    criar = MagicMock(return_value=("evento-teste", "https://meet.google.com/teste"))
    remover = MagicMock(return_value=True)

    import app.services.google_calendar
    import app.services.gerar_agenda
    import app.routes.aulas
    import app.routes.portal
    import app.routes.turmas

    monkeypatch.setattr(app.services.google_calendar, "criar_evento", criar)
    monkeypatch.setattr(app.services.google_calendar, "remover_evento_google", remover)
    monkeypatch.setattr(app.services.gerar_agenda, "criar_evento", criar)
    monkeypatch.setattr(app.routes.aulas, "criar_evento", criar)
    monkeypatch.setattr(app.routes.aulas, "remover_evento_google", remover)
    monkeypatch.setattr(app.routes.portal, "criar_evento", criar)
    monkeypatch.setattr(app.routes.portal, "remover_evento_google", remover)
    monkeypatch.setattr(app.routes.turmas, "criar_evento", criar)
    monkeypatch.setattr(app.routes.turmas, "criar_evento_google", criar)
    monkeypatch.setattr(app.routes.turmas, "remover_evento_google", remover)

    return {"criar": criar, "remover": remover}
