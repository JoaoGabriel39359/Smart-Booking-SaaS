from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from app.models import TipoAluno

class AlunoBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
    model_config = ConfigDict(from_attributes=True)
    nome: Optional[str] = None
    sobrenome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    tipo: Optional[TipoAluno] = None
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None

class TurmaCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nome_turma: str
    tipo: str
    dia_semana: str
    horario: str
    aluno_ids: List[int] = []

class TurmaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome_turma: str
    tipo: str