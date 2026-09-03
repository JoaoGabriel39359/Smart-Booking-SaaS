export type TipoAluno = "VIP" | "DUO" | "TEAM";

export interface Aluno {
  id: number;
  nome: string;
  sobrenome: string;
  telefone: string;
  email?: string | null;
  tipo: TipoAluno;
  endereco?: string | null;
  cidade?: string | null;
  estado?: string | null;
  turma_id?: number | null;
  limite_aulas_semana?: number;
  creditos_reposicao?: number;
  token_acesso?: string | null;
}

export interface Professor {
  id: number;
  nome: string;
  telefone?: string | null;
  cor?: string | null;
  ativo: boolean;
  total_turnos: number;
  total_turmas: number;
}

export interface HorarioTurma {
  dia: number;
  hora: string;
}

export interface Turma {
  id: number;
  nome_turma: string;
  tipo: TipoAluno;
  dia_semana?: string | null;
  horario?: string | null;
  capacidade_maxima: number;
  duracao_minutos: number;
  meet_link?: string | null;
  professor_id?: number | null;
  professor_nome?: string | null;
  horarios: HorarioTurma[];
  alunos: Pick<Aluno, "id" | "nome" | "sobrenome">[];
}

export interface Grade {
  id: number;
  dia_semana: number;
  hora_inicio: string;
  hora_fim: string;
  ativo: boolean;
  professor_id?: number | null;
  nome_professor?: string | null;
  capacidade: number;
}

export interface AgendaAluno {
  aula_id: number;
  aluno_id: number;
  nome: string;
}

export interface SessaoAgenda {
  data_inicio: string;
  turma_id?: number | null;
  status: string;
  nome_exibicao: string;
  tipo: "TURMA" | "VIP";
  is_turma: boolean;
  professor_id?: number | null;
  professor_nome?: string | null;
  professor_cor?: string | null;
  alunos: AgendaAluno[];
}

export interface SessaoHistorico {
  data: string;
  nome_exibicao: string;
  is_turma: boolean;
  turma_id?: number | null;
  professor_nome?: string | null;
  alunos: Array<{
    historico_id: number;
    nome: string;
    status_presenca: boolean;
    desempenho?: string | null;
    observacao?: string | null;
    chamada_realizada: boolean;
  }>;
}

export interface Frequencia {
  aluno_id: number;
  nome: string;
  total_aulas: number;
  presencas: number;
  faltas: number;
  cancelamentos: number;
  taxa_presenca: number;
  ultima_aula: string;
}

export interface Cancelamento {
  aula_id: number;
  aluno_id: number;
  nome: string;
  telefone: string;
  data_aula: string;
  data_cancelamento: string;
  gerou_credito: boolean;
  credito_consumido: boolean;
  validade_reposicao?: string | null;
  situacao_credito: string;
}

export interface Credito {
  aluno_id: number;
  nome: string;
  telefone: string;
  creditos_validos: number;
  validade_proxima: string;
  vencidos: number;
}

export interface PortalData {
  aluno: {
    id: number;
    nome: string;
    sobrenome: string;
    telefone: string;
    email?: string | null;
    token: string;
    tipo: TipoAluno;
    creditos_reposicao: number;
  };
  aulas: Array<{
    id: number;
    data_inicio: string;
    data_fim?: string | null;
    eh_reposicao: boolean;
    professor_nome?: string | null;
  }>;
}

export interface Slot {
  hora: string;
  grade_id: number;
  vagas: number;
}

export interface RelatorioRegistro {
  id: number;
  data_inicio: string;
  presente: boolean;
  status: "Presente" | "Ausente";
  desempenho: string;
  observacao: string;
  turma?: string | null;
  professor?: string | null;
  eh_reposicao: boolean;
}

export interface RelatorioAluno {
  aluno: {
    id: number;
    nome: string;
    tipo: TipoAluno;
    turma?: string | null;
  };
  resumo: {
    total_aulas: number;
    presencas: number;
    faltas: number;
    taxa_presenca: number;
  };
  registros: RelatorioRegistro[];
}
