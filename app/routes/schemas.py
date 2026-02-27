from pydantic import BaseModel
from typing import Optional
from app.models import TipoAluno

# Campos que são comuns tanto na criação quanto na edição
class AlunoBase(BaseModel):
    nome: str
    sobrenome: str
    telefone: str
    email: str
    tipo: TipoAluno = TipoAluno.VIP 
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None

class AlunoCreate(AlunoBase):
    turma_id: Optional[int] = None

class AlunoEdit(BaseModel):
    nome: str
    sobrenome: Optional[str] = None
    telefone: str
    email: Optional[str] = None
    tipo: Optional[TipoAluno] = None  # <-- Aqui precisa ser o nome da sua classe Enum, não 'str'
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None

    class Config:
        from_attributes = True

class TurmaCreate(BaseModel):
    nome_turma: str  # <--- Garanta que aqui é nome_turma
    tipo: str
    dia_semana: str
    horario: str
    aluno_ids: list[int] = []

class TurmaResponse(BaseModel):
    id: int
    nome_turma: str
    tipo: str
    
    class Config:
        from_attributes = True