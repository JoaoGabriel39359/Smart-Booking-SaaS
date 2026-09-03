import { useEffect, useState, type FormEvent } from "react";
import { CalendarDays, CalendarPlus, CheckCircle2, Clock3, X } from "lucide-react";
import { api, errorMessage, query } from "../services/api";
import type { AgendaAluno, Aluno, Grade, SessaoAgenda } from "../types";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Loading,
  Modal,
  Notice,
  SelectField,
} from "../components/ui";

type ChamadaState = { nome: string; alunos: AgendaAluno[] } | null;
type Presencas = Record<number, "presente" | "ausente">;

export default function AgendaScreen() {
  const [sessoes, setSessoes] = useState<SessaoAgenda[]>([]);
  const [alunos, setAlunos] = useState<Aluno[]>([]);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ text: string; kind: "error" | "success" } | null>(null);
  const [chamada, setChamada] = useState<ChamadaState>(null);
  const [presencas, setPresencas] = useState<Presencas>({});
  const [avulsaOpen, setAvulsaOpen] = useState(false);
  const [desempenho, setDesempenho] = useState("Bom");
  const [observacao, setObservacao] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [agenda, listaAlunos, listaGrades] = await Promise.all([
        api.get<SessaoAgenda[]>("/aulas/lista-professor"),
        api.get<Aluno[]>("/alunos/"),
        api.get<Grade[]>("/aulas/grade"),
      ]);
      setSessoes(agenda);
      setAlunos(listaAlunos);
      setGrades(listaGrades);
    } catch (err) {
      setMessage({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function abrirChamada(sessao: SessaoAgenda) {
    setChamada({ nome: sessao.nome_exibicao, alunos: sessao.alunos });
    setPresencas(Object.fromEntries(sessao.alunos.map((aluno) => [aluno.aula_id, "presente"])));
    setDesempenho("Bom");
    setObservacao("");
  }

  async function salvarChamada(event: FormEvent) {
    event.preventDefault();
    if (!chamada) return;
    try {
      await Promise.all(chamada.alunos.map((aluno) => api.patch(query(
        `/aulas/${aluno.aula_id}/presenca`,
        {
          status: presencas[aluno.aula_id] ?? "presente",
          desempenho,
          observacao,
        },
      ))));
      setChamada(null);
      setMessage({ text: "Chamada registrada com sucesso.", kind: "success" });
      await load();
    } catch (err) {
      setMessage({ text: errorMessage(err), kind: "error" });
    }
  }

  async function cancelarSessao(sessao: SessaoAgenda) {
    if (!confirm(`Excluir a aula de ${sessao.nome_exibicao}?`)) return;
    try {
      await api.delete(query("/aulas/cancelar-grupo", {
        data_inicio: sessao.data_inicio,
        turma_id: sessao.turma_id,
        aluno_id: sessao.turma_id ? null : sessao.alunos[0]?.aluno_id,
      }));
      setMessage({ text: "Aula removida da agenda.", kind: "success" });
      await load();
    } catch (err) {
      setMessage({ text: errorMessage(err), kind: "error" });
    }
  }

  async function criarAvulsa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/aulas/avulsa", {
        aluno_id: Number(form.get("aluno_id")),
        data_inicio: form.get("data_inicio"),
        grade_id: form.get("grade_id") || null,
      });
      setAvulsaOpen(false);
      setMessage({ text: "Aula individual criada.", kind: "success" });
      await load();
    } catch (err) {
      setMessage({ text: errorMessage(err), kind: "error" });
    }
  }

  return (
    <>
      {message && <Notice message={message.text} kind={message.kind} />}
      <Card className="agenda-panel">
        <div className="agenda-panel__header">
          <h1><CalendarDays size={22} /> Próximas Aulas</h1>
          <Button onClick={() => setAvulsaOpen(true)}>
            <CalendarPlus size={16} /> Nova Aula Individual
          </Button>
        </div>

        <div className="agenda-panel__body">
          {loading ? <Loading /> : sessoes.length === 0 ? (
            <Empty text="Nenhuma aula futura encontrada." />
          ) : (
            <div className="agenda-grid">
              {sessoes.map((sessao) => {
                const data = new Date(sessao.data_inicio);
                const liberada = Date.now() >= data.getTime();
                const chave = `${sessao.data_inicio}-${sessao.turma_id ?? sessao.alunos[0]?.aluno_id}`;
                return (
                  <article
                    className="agenda-card"
                    key={chave}
                    style={{ borderLeftColor: sessao.professor_cor || undefined }}
                  >
                    <div className="agenda-card__main">
                      <div className="agenda-card__title">
                        <h2>{sessao.nome_exibicao}</h2>
                        <Badge tone="indigo">
                          {sessao.tipo === "TURMA" ? `TURMA (${sessao.alunos.length})` : "VIP"}
                        </Badge>
                      </div>
                      <div className="agenda-card__meta">
                        <span>
                          <CalendarDays size={14} />
                          {data.toLocaleDateString("pt-BR", {
                            weekday: "short",
                            day: "2-digit",
                            month: "long",
                          })}
                        </span>
                        <span>
                          <Clock3 size={14} />
                          {data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      {sessao.professor_nome && (
                        <small className="agenda-card__teacher">Professor: {sessao.professor_nome}</small>
                      )}
                    </div>
                    <div className="agenda-card__actions">
                      <Button
                        className={!liberada ? "button--locked" : ""}
                        disabled={!liberada}
                        onClick={() => abrirChamada(sessao)}
                      >
                        {liberada && <CheckCircle2 size={15} />}
                        {liberada ? "Chamada" : "Bloqueado"}
                      </Button>
                      <button
                        className="agenda-card__remove"
                        onClick={() => void cancelarSessao(sessao)}
                        title="Excluir aula"
                        aria-label={`Excluir aula de ${sessao.nome_exibicao}`}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={Boolean(chamada)}
        title="Registrar chamada"
        description={chamada?.nome}
        onClose={() => setChamada(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setChamada(null)}>Cancelar</Button>
            <Button type="submit" form="form-chamada">Salvar chamada</Button>
          </>
        }
      >
        <form id="form-chamada" className="form-grid" onSubmit={salvarChamada}>
          <div className="attendance-list span-2">
            {chamada?.alunos.map((aluno) => (
              <label className="attendance-row" key={aluno.aula_id}>
                <strong>{aluno.nome}</strong>
                <select
                  value={presencas[aluno.aula_id] ?? "presente"}
                  onChange={(event) => setPresencas((current) => ({
                    ...current,
                    [aluno.aula_id]: event.target.value as "presente" | "ausente",
                  }))}
                >
                  <option value="presente">Presente</option>
                  <option value="ausente">Ausente</option>
                </select>
              </label>
            ))}
          </div>
          <SelectField className="span-2" label="Desempenho" value={desempenho} onChange={(e) => setDesempenho(e.target.value)}>
            <option>Excelente</option><option>Bom</option><option>Regular</option><option>Precisa melhorar</option>
          </SelectField>
          <label className="field span-2">
            <span>Observação pedagógica</span>
            <textarea value={observacao} onChange={(e) => setObservacao(e.target.value)} />
          </label>
        </form>
      </Modal>

      <Modal
        open={avulsaOpen}
        title="Nova aula individual"
        description="O horário será validado novamente no momento do cadastro."
        onClose={() => setAvulsaOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAvulsaOpen(false)}>Cancelar</Button>
            <Button type="submit" form="form-avulsa">Agendar</Button>
          </>
        }
      >
        <form id="form-avulsa" className="form-grid" onSubmit={criarAvulsa}>
          <SelectField className="span-2" label="Aluno" name="aluno_id" required defaultValue="">
            <option value="" disabled>Selecione...</option>
            {alunos.map((aluno) => <option key={aluno.id} value={aluno.id}>{aluno.nome} {aluno.sobrenome}</option>)}
          </SelectField>
          <Field label="Data e hora" name="data_inicio" type="datetime-local" required />
          <SelectField label="Turno / professor" name="grade_id" defaultValue="">
            <option value="">Sem turno específico</option>
            {grades.filter((grade) => grade.ativo).map((grade) => (
              <option key={grade.id} value={grade.id}>
                {grade.nome_professor ?? "Sem professor"} · {grade.hora_inicio}–{grade.hora_fim}
              </option>
            ))}
          </SelectField>
        </form>
      </Modal>
    </>
  );
}
