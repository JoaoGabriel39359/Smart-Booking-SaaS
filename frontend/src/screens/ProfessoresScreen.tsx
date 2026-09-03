import { useEffect, useMemo, useState, type FormEvent } from "react";
import { BookOpen, CalendarClock, Edit3, Eye, Phone, Plus, Search, Trash2, Users } from "lucide-react";
import { api, errorMessage } from "../services/api";
import type { Grade, Professor, Turma } from "../types";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Loading,
  Modal,
  Notice,
  PageHeader,
  SelectField,
} from "../components/ui";

const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

export default function ProfessoresScreen() {
  const [professores, setProfessores] = useState<Professor[]>([]);
  const [turmas, setTurmas] = useState<Turma[]>([]);
  const [grade, setGrade] = useState<Grade[]>([]);
  const [selected, setSelected] = useState<Professor | null | undefined>(undefined);
  const [details, setDetails] = useState<Professor | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [listaProfessores, listaTurmas, listaGrade] = await Promise.all([
        api.get<Professor[]>("/professores/"),
        api.get<Turma[]>("/turmas/"),
        api.get<Grade[]>("/aulas/grade"),
      ]);
      setProfessores(listaProfessores);
      setTurmas(listaTurmas);
      setGrade(listaGrade);
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filtrados = useMemo(() => {
    const term = search.toLocaleLowerCase("pt-BR");
    return professores.filter((professor) =>
      `${professor.nome} ${professor.telefone ?? ""}`.toLocaleLowerCase("pt-BR").includes(term),
    );
  }, [professores, search]);

  const turmasDoProfessor = (id: number) => turmas.filter((turma) => turma.professor_id === id);
  const turnosDoProfessor = (id: number) => grade.filter((turno) => turno.professor_id === id && turno.ativo);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      nome: String(form.get("nome")),
      telefone: String(form.get("telefone") ?? "") || null,
      cor: String(form.get("cor") ?? "#5b5bd6"),
      ativo: form.get("ativo") === "true",
    };
    try {
      if (selected) await api.put(`/professores/${selected.id}`, payload);
      else await api.post("/professores/", payload);
      setSelected(undefined);
      setNotice({ text: "Professor salvo com sucesso.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function remove(professor: Professor) {
    if (!confirm(`Excluir ${professor.nome}? Se houver aulas futuras, prefira desativar.`)) return;
    try {
      await api.delete(`/professores/${professor.id}`);
      setNotice({ text: "Professor removido.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  return (
    <>
      <PageHeader
        title="Gestão de professores"
        description="Equipe, disponibilidade e separação das turmas por professor responsável."
        actions={<Button onClick={() => setSelected(null)}><Plus size={17} /> Novo professor</Button>}
      />
      {notice && <Notice message={notice.text} kind={notice.kind} />}
      <Card className="teachers-panel">
        <div className="card__body">
          <div className="toolbar">
            <div className="search-wrap">
              <Search size={17} />
              <input className="search-input" placeholder="Buscar professor..." value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
            <span className="teachers-total">{professores.filter((professor) => professor.ativo).length} ativo(s)</span>
          </div>
          {loading ? <Loading /> : filtrados.length === 0 ? <Empty /> : (
            <div className="teachers-grid">
              {filtrados.map((professor) => {
                const classes = turmasDoProfessor(professor.id);
                const turnos = turnosDoProfessor(professor.id);
                return (
                  <article className="teacher-card" key={professor.id} style={{ "--teacher-color": professor.cor ?? "#6366f1" } as React.CSSProperties}>
                    <div className="teacher-card__header">
                      <div className="teacher-card__identity">
                        <span className="teacher-card__avatar">{professor.nome.trim().charAt(0).toUpperCase()}</span>
                        <div><strong>{professor.nome}</strong><span><Phone size={11} /> {professor.telefone || "Não informado"}</span></div>
                      </div>
                      <Badge tone={professor.ativo ? "green" : "neutral"}>{professor.ativo ? "Ativo" : "Inativo"}</Badge>
                    </div>
                    <div className="teacher-card__numbers">
                      <span><Users size={15} /><strong>{classes.length}</strong> turma(s)</span>
                      <span><CalendarClock size={15} /><strong>{turnos.length}</strong> turno(s)</span>
                    </div>
                    <div className="teacher-card__classes">
                      <small>Turmas deste professor</small>
                      {classes.length === 0 ? <span className="teacher-empty">Nenhuma turma vinculada</span> : classes.slice(0, 3).map((turma) => (
                        <span className="teacher-class-chip" key={turma.id}>{turma.nome_turma}</span>
                      ))}
                      {classes.length > 3 && <span className="teacher-class-more">+{classes.length - 3} outra(s)</span>}
                    </div>
                    <div className="teacher-card__actions">
                      <Button variant="secondary" onClick={() => setDetails(professor)}><Eye size={14} /> Ver turmas</Button>
                      <button type="button" className="teacher-action" title="Editar professor" onClick={() => setSelected(professor)}><Edit3 size={16} /></button>
                      <button type="button" className="teacher-action teacher-action--delete" title="Excluir professor" onClick={() => void remove(professor)}><Trash2 size={16} /></button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={selected !== undefined}
        title={selected ? "Editar professor" : "Novo professor"}
        onClose={() => setSelected(undefined)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelected(undefined)}>Cancelar</Button>
            <Button type="submit" form="form-professor">Salvar</Button>
          </>
        }
      >
        <form id="form-professor" className="form-grid" onSubmit={save}>
          <Field className="span-2" label="Nome completo" name="nome" defaultValue={selected?.nome ?? ""} required />
          <Field label="Telefone" name="telefone" defaultValue={selected?.telefone ?? ""} />
          <Field label="Cor na agenda" name="cor" type="color" defaultValue={selected?.cor ?? "#5b5bd6"} />
          <SelectField className="span-2" label="Situação" name="ativo" defaultValue={String(selected?.ativo ?? true)}>
            <option value="true">Ativo</option>
            <option value="false">Inativo</option>
          </SelectField>
        </form>
      </Modal>

      <Modal
        open={Boolean(details)}
        title={details ? `Turmas de ${details.nome}` : "Detalhes do professor"}
        description="As turmas do professor ficam separadas das turmas atribuídas a outros responsáveis."
        onClose={() => setDetails(null)}
        wide
        footer={<Button variant="secondary" onClick={() => setDetails(null)}>Fechar</Button>}
      >
        {details && (() => {
          const proprias = turmasDoProfessor(details.id);
          const turnos = turnosDoProfessor(details.id);
          const outras = turmas.filter((turma) => turma.professor_id !== details.id);
          return (
            <div className="teacher-details">
              <div className="teacher-details__summary">
                <div><BookOpen size={18} /><span>Turmas próprias</span><strong>{proprias.length}</strong></div>
                <div><CalendarClock size={18} /><span>Turnos ativos</span><strong>{turnos.length}</strong></div>
              </div>
              <section className="teacher-details__section teacher-details__section--own">
                <h3>Turmas deste professor</h3>
                {proprias.length === 0 ? <Empty text="Nenhuma turma vinculada a este professor." /> : (
                  <div className="teacher-class-list">
                    {proprias.map((turma) => (
                      <article key={turma.id}>
                        <div><strong>{turma.nome_turma}</strong><Badge tone="indigo">{turma.tipo}</Badge></div>
                        <span>{turma.alunos.length}/{turma.capacidade_maxima} aluno(s)</span>
                        <small>{turma.horarios.length ? turma.horarios.map((horario) => `${DIAS[horario.dia]} ${horario.hora}`).join(" · ") : "Horário não informado"}</small>
                      </article>
                    ))}
                  </div>
                )}
              </section>
              <section className="teacher-details__section">
                <h3>Disponibilidade na grade</h3>
                {turnos.length === 0 ? <p className="teacher-details__empty">Nenhum turno ativo na grade base.</p> : (
                  <div className="teacher-slots">
                    {turnos.map((turno) => <span key={turno.id}>{DIAS[turno.dia_semana]} · {turno.hora_inicio}–{turno.hora_fim} · {turno.capacidade} vaga(s)</span>)}
                  </div>
                )}
              </section>
              <section className="teacher-details__section teacher-details__section--others">
                <h3>Turmas de outros professores</h3>
                {outras.length === 0 ? <p className="teacher-details__empty">Não há outras turmas cadastradas.</p> : (
                  <div className="other-teacher-classes">
                    {outras.map((turma) => (
                      <div key={turma.id}><strong>{turma.nome_turma}</strong><span>{turma.professor_nome ?? "Sem professor definido"}</span></div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          );
        })()}
      </Modal>
    </>
  );
}
