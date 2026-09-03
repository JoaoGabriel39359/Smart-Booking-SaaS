import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum, Time
from sqlalchemy.orm import relationship
import enum
from app.database import Base

# Definindo os tipos de Aluno e Status de Aula
class TipoAluno(enum.Enum):
    VIP = "VIP"
    DUO = "DUO"
    TEAM = "TEAM"

class StatusAula(enum.Enum):
    marcada = "marcada"
    presente = "Presente"
    ausente = "Ausente"
    cancelado = "Cancelado"

class Professor(Base):
    __tablename__ = "professores"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=True)
    cor = Column(String, nullable=True)
    ativo = Column(Boolean, default=True)

    turnos = relationship("GradeProfessor", back_populates="professor")
    aulas = relationship("Aula", back_populates="professor")
    turmas = relationship("Turma", back_populates="professor")

class Aluno(Base):
    __tablename__ = "alunos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    sobrenome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    token_acesso = Column(String, default=lambda: str(uuid.uuid4()), unique=True)
    
    endereco = Column(String, nullable=True)
    cidade = Column(String, nullable=True)
    estado = Column(String, nullable=True)

    tipo = Column(Enum(TipoAluno), default=TipoAluno.VIP)
    limite_aulas_semana = Column(Integer, default=2) 
    creditos_reposicao = Column(Integer, default=0) 

    turma_id = Column(Integer, ForeignKey("turmas.id"), nullable=True)
    turma = relationship("Turma", back_populates="alunos")
    aulas = relationship("Aula", back_populates="aluno")

    horarios = relationship("HorarioAula", back_populates="aluno")
    historico = relationship("HistoricoAula", back_populates="aluno")

class Aula(Base):
    __tablename__ = "aulas"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"))
    turma_id = Column(Integer, ForeignKey("turmas.id"), nullable=True) 
    professor_id = Column(Integer, ForeignKey("professores.id"), nullable=True, index=True)
    
    lembrete_enviado = Column(Boolean, default=False)
    lembrete_10h_enviado = Column(Boolean, default=False)
    data_inicio = Column(DateTime)
    data_fim = Column(DateTime, nullable=True)
    status = Column(Enum(StatusAula), default=StatusAula.marcada)
    desempenho = Column(String, nullable=True)
    tipo = Column(String, nullable=True)

    conteudo_dado = Column(String, nullable=True)
    observacoes = Column(String, nullable=True)
    eh_reposicao = Column(Boolean, default=False) 
    validade_reposicao = Column(DateTime, nullable=True) 
    cancelada_em = Column(DateTime, nullable=True, index=True)
    credito_consumido_em = Column(DateTime, nullable=True, index=True)
    google_event_id = Column(String, nullable=True)

    aluno = relationship("Aluno", back_populates="aulas")
    turma = relationship("Turma")
    professor = relationship("Professor", back_populates="aulas")
    historicos = relationship("HistoricoAula", back_populates="aula", cascade="all, delete-orphan")

class Turma(Base):
    __tablename__ = "turmas"
    id = Column(Integer, primary_key=True, index=True)
    nome_turma = Column(String, nullable=False)
    tipo = Column(String, default="TEAM")       # VIP, DUO, TEAM
    dia_semana = Column(String, nullable=True)
    horario = Column(String, nullable=True)
    capacidade_maxima = Column(Integer, default=6)
    duracao_minutos = Column(Integer, default=60)
    meet_link = Column(String, nullable=True)
    professor_id = Column(Integer, ForeignKey("professores.id"), nullable=True)

    alunos = relationship("Aluno", back_populates="turma")
    horarios = relationship("HorarioAula", back_populates="turma")
    professor = relationship("Professor", back_populates="turmas")

class GradeProfessor(Base):
    __tablename__ = "grade_professor"
    id = Column(Integer, primary_key=True, index=True)
    dia_semana = Column(Integer)
    hora_inicio = Column(String)
    hora_fim = Column(String)
    ativo = Column(Boolean, default=True)
    professor_id = Column(Integer, ForeignKey("professores.id"), nullable=True, index=True)
    capacidade = Column(Integer, default=1, nullable=False)

    professor = relationship("Professor", back_populates="turnos")

class Conversa(Base):
    __tablename__ = "conversas"
    id = Column(Integer, primary_key=True, index=True)
    telefone = Column(String, unique=True, index=True)
    etapa = Column(String, default="menu")
    data_escolhida = Column(String, nullable=True)

class HorarioAula(Base):
    __tablename__ = 'horarios_aula'
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey('alunos.id'))
    turma_id = Column(Integer, ForeignKey('turmas.id'))
    dia_da_semana = Column(Integer)  
    horario = Column(Time, nullable=False) 

    aluno = relationship("Aluno", back_populates="horarios")
    turma = relationship("Turma", back_populates="horarios")

class HistoricoAula(Base):
    __tablename__ = 'historico_aulas'
    id = Column(Integer, primary_key=True)
    aula_id = Column(Integer, ForeignKey("aulas.id", ondelete="CASCADE"), nullable=True, index=True)
    aluno_id = Column(Integer, ForeignKey('alunos.id'))
    data_aula = Column(DateTime, nullable=False)
    status_presenca = Column(Boolean, default=False)
    observacao = Column(String)
    desempenho = Column(String)
    google_event_id = Column(String, nullable=True)
    chamada_realizada = Column(Boolean, default=False)

    aluno = relationship("Aluno", back_populates="historico")
    aula = relationship("Aula", back_populates="historicos")
