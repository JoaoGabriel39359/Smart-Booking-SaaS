import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CalendarSync, Edit3, Plus, Search, Trash2, X } from "lucide-react";
import { api, errorMessage } from "../services/api";
import type { Aluno, HorarioTurma, Professor, TipoAluno, Turma } from "../types";
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

const dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

interface Draft {
  turma?: Turma;
  nome_turma: string;
  tipo: TipoAluno;
  duracao_minutos: number;
  professor_id: string;
  meet_link: string;
  horarios: HorarioTurma[];
  aluno_ids: number[];
}

const emptyDraft = (): Draft => ({
  nome_turma: "",
  tipo: "TEAM",
  duracao_minutos: 60,
  professor_id: "",
  meet_link: "",
  horarios: [],
  aluno_ids: [],
});

export default function TurmasScreen() {
  const [turmas, setTurmas] = useState<Turma[]>([]);
  const [alunos, setAlunos] = useState<Aluno[]>([]);
  const [professores, setProfessores] = useState<Professor[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [novoDia, setNovoDia] = useState("0");
  const [novaHora, setNovaHora] = useState("08:00");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [listaTurmas, listaAlunos, listaProfessores] = await Promise.all([
        api.get<Turma[]>("/turmas/"),
        api.get<Aluno[]>("/alunos/"),
        api.get<Professor[]>("/professores/"),
      ]);
      setTurmas(listaTurmas);
      setAlunos(listaAlunos);
      setProfessores(listaProfessores);
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filtradas = useMemo(() => {
    const term = search.toLocaleLowerCase("pt-BR");
    return turmas.filter((turma) =>
      `${turma.nome_turma} ${turma.tipo} ${turma.professor_nome ?? ""}`
        .toLocaleLowerCase("pt-BR").includes(term),
    );
  }, [turmas, search]);

  function edit(turma: Turma) {
    setDraft({
      turma,
      nome_turma: turma.nome_turma,
      tipo: turma.tipo,
      duracao_minutos: turma.duracao_minutos || 60,
      professor_id: turma.professor_id ? String(turma.professor_id) : "",
      meet_link: turma.meet_link ?? "",
      horarios: [...(turma.horarios ?? [])],
      aluno_ids: turma.alunos.map((aluno) => aluno.id),
    });
  }

  function addHorario() {
    if (!draft || !novaHora) return;
    const item = { dia: Number(novoDia), hora: novaHora };
    if (draft.horarios.some((h) => h.dia === item.dia && h.hora === item.hora)) return;
    setDraft({ ...draft, horarios: [...draft.horarios, item].sort((a, b) => a.dia - b.dia || a.hora.localeCompare(b.hora)) });
  }

  function toggleAluno(id: number) {
    if (!draft) return;
    setDraft({
      ...draft,
      aluno_ids: draft.aluno_ids.includes(id)
        ? draft.aluno_ids.filter((alunoId) => alunoId !== id)
        : [...draft.aluno_ids, id],
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    if (!draft.horarios.length) {
      setNotice({ text: "Adicione ao menos um dia e horário.", kind: "error" });
      return;
    }
    const payload = {
      nome_turma: draft.nome_turma,
      tipo: draft.tipo,
      duracao_minutos: draft.duracao_minutos,
      professor_id: draft.professor_id ? Number(draft.professor_id) : null,
      meet_link: draft.meet_link || null,
      horarios: draft.horarios,
      aluno_ids: draft.aluno_ids,
    };
    try {
      if (draft.turma) await api.put(`/turmas/${draft.turma.id}`, payload);
      else await api.post("/turmas/", payload);
      setDraft(null);
      setNotice({ text: "Turma salva e agenda futura sincronizada.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function remove(turma: Turma) {
    if (!confirm(`Excluir ${turma.nome_turma}? Aulas realizadas e créditos serão preservados.`)) return;
    try {
      await api.delete(`/turmas/${turma.id}`);
      setNotice({ text: "Turma removida; histórico e créditos foram preservados.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function generate() {
    if (!confirm("Gerar e sincronizar as próximas quatro semanas?")) return;
    try {
      await api.post("/turmas/gerar-mensal");
      setNotice({ text: "Agenda mensal sincronizada.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Organização recorrente"
        title="Turmas"
        description="Edite composição, duração, horários e professor sem destruir o histórico nem os créditos."
        actions={
          <>
            <Button variant="secondary" onClick={() => void generate()}><CalendarSync size={17} /> Gerar mês</Button>
            <Button onClick={() => setDraft(emptyDraft())}><Plus size={17} /> Nova turma</Button>
          </>
        }
      />
      {notice && <Notice message={notice.text} kind={notice.kind} />}
      <Card>
        <div className="card__body">
          <div className="toolbar">
            <div className="search-wrap">
              <Search size={17} />
              <input className="search-input" placeholder="Buscar turma ou professor..." value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
          </div>
          {loading ? <Loading /> : filtradas.length === 0 ? <Empty /> : (
            <div className="grid grid--cards">
              {filtradas.map((turma) => (
                <Card className="data-card" key={turma.id}>
                  <div className="data-card__top">
                    <div><h3>{turma.nome_turma}</h3><p>{turma.professor_nome ?? "Professor não definido"}</p></div>
                    <Badge tone="indigo">{turma.tipo}</Badge>
                  </div>
                  <div className="data-card__meta">
                    <Badge>{turma.alunos.length}/{turma.capacidade_maxima} alunos</Badge>
                    <Badge tone="orange">{turma.duracao_minutos} min</Badge>
                  </div>
                  <p>{turma.horarios?.map((h) => `${dias[h.dia]} ${h.hora}`).join(" · ") || "Sem horário"}</p>
                  <div className="data-card__actions">
                    <Button variant="secondary" onClick={() => edit(turma)}><Edit3 size={14} /> Editar</Button>
                    <Button variant="danger" onClick={() => void remove(turma)}><Trash2 size={14} /></Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={Boolean(draft)}
        title={draft?.turma ? "Editar turma" : "Nova turma"}
        description="Mudanças estruturais regeneram somente os agendamentos futuros."
        onClose={() => setDraft(null)}
        wide
        footer={
          <>
            <Button variant="secondary" onClick={() => setDraft(null)}>Cancelar</Button>
            <Button type="submit" form="form-turma">Salvar turma</Button>
          </>
        }
      >
        {draft && (
          <form id="form-turma" className="form-grid" onSubmit={save}>
            <Field label="Nome da turma" value={draft.nome_turma} onChange={(e) => setDraft({ ...draft, nome_turma: e.target.value })} required />
            <SelectField label="Plano" value={draft.tipo} onChange={(e) => setDraft({ ...draft, tipo: e.target.value as TipoAluno })}>
              <option value="VIP">VIP</option><option value="DUO">DUO</option><option value="TEAM">TEAM</option>
            </SelectField>
            <SelectField label="Duração" value={draft.duracao_minutos} onChange={(e) => setDraft({ ...draft, duracao_minutos: Number(e.target.value) })}>
              <option value={60}>1 hora</option><option value={90}>1h30</option><option value={120}>2 horas</option>
            </SelectField>
            <SelectField label="Professor" value={draft.professor_id} onChange={(e) => setDraft({ ...draft, professor_id: e.target.value })}>
              <option value="">Sem professor</option>
              {professores.filter((p) => p.ativo).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </SelectField>
            <Field className="span-2" label="Link do Meet" value={draft.meet_link} onChange={(e) => setDraft({ ...draft, meet_link: e.target.value })} />
            <div className="span-2 field">
              <span>Horários semanais</span>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8 }}>
                <select value={novoDia} onChange={(e) => setNovoDia(e.target.value)}>
                  {dias.map((dia, index) => <option key={dia} value={index}>{dia}</option>)}
                </select>
                <input type="time" value={novaHora} onChange={(e) => setNovaHora(e.target.value)} />
                <Button type="button" onClick={addHorario}><Plus size={15} /></Button>
              </div>
              <div className="data-card__meta">
                {draft.horarios.map((h) => (
                  <Badge key={`${h.dia}-${h.hora}`} tone="indigo">
                    {dias[h.dia]} {h.hora}
                    <button
                      type="button"
                      aria-label="Remover horário"
                      style={{ border: 0, background: "transparent", padding: 0, display: "grid" }}
                      onClick={() => setDraft({ ...draft, horarios: draft.horarios.filter((item) => item !== h) })}
                    ><X size={12} /></button>
                  </Badge>
                ))}
              </div>
            </div>
            <div className="span-2 field">
              <span>Alunos da turma</span>
              <div className="check-list">
                {alunos.map((aluno) => (
                  <label className="check-row" key={aluno.id}>
                    <input type="checkbox" checked={draft.aluno_ids.includes(aluno.id)} onChange={() => toggleAluno(aluno.id)} />
                    <span>{aluno.nome} {aluno.sobrenome} · {aluno.tipo}</span>
                  </label>
                ))}
              </div>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
