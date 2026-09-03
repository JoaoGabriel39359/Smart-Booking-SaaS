import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CheckCircle2, Eye, Search } from "lucide-react";
import { api, errorMessage, query } from "../services/api";
import type { SessaoHistorico } from "../types";
import {
  Badge,
  Button,
  Card,
  Empty,
  Loading,
  Modal,
  Notice,
  PageHeader,
  SelectField,
  Stat,
} from "../components/ui";

interface Stats {
  taxa_presenca: number;
  total_aulas: number;
  alunos_faltosos: Array<{ nome: string; faltas: number }>;
}

export default function HistoricoScreen() {
  const [finalizadas, setFinalizadas] = useState(false);
  const [sessoes, setSessoes] = useState<SessaoHistorico[]>([]);
  const [stats, setStats] = useState<Stats>({ taxa_presenca: 0, total_aulas: 0, alunos_faltosos: [] });
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" } | null>(null);
  const [registro, setRegistro] = useState<SessaoHistorico | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [historico, estatisticas] = await Promise.all([
        api.get<SessaoHistorico[]>(query("/aulas/admin/historico-geral", { finalizadas })),
        api.get<Stats>("/aulas/admin/estatisticas-mes"),
      ]);
      setSessoes(historico);
      setStats(estatisticas);
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [finalizadas]);

  const filtradas = useMemo(() => {
    const term = search.toLocaleLowerCase("pt-BR").trim();
    if (!term) return sessoes;
    return sessoes.filter((sessao) => {
      const data = new Date(sessao.data).toLocaleString("pt-BR");
      return `${sessao.nome_exibicao} ${sessao.professor_nome ?? ""} ${data} ${sessao.alunos.map((aluno) => aluno.nome).join(" ")}`
        .toLocaleLowerCase("pt-BR").includes(term);
    });
  }, [sessoes, search]);

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!registro) return;
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      await Promise.all(registro.alunos.map((aluno) => api.patch(query(
        `/aulas/admin/presenca-retroativa/${aluno.historico_id}`,
        {
          status: String(form.get(`status-${aluno.historico_id}`) ?? "presente"),
          desempenho: String(form.get(`desempenho-${aluno.historico_id}`) ?? "Bom"),
          observacao: String(form.get(`observacao-${aluno.historico_id}`) ?? ""),
        },
      ))));
      setRegistro(null);
      setNotice({ text: finalizadas ? "Chamada corrigida com sucesso." : "Chamada registrada com sucesso.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setSaving(false);
    }
  }

  function trocarLista(valor: boolean) {
    setFinalizadas(valor);
    setRegistro(null);
  }

  return (
    <>
      <PageHeader
        title="Histórico de aulas"
        description="Acompanhe pendências, consulte chamadas concluídas e corrija os registros de toda a turma."
        actions={
          <div className="history-switch" aria-label="Filtrar histórico">
            <button type="button" className={!finalizadas ? "active" : ""} onClick={() => trocarLista(false)}>Pendentes</button>
            <button type="button" className={finalizadas ? "active" : ""} onClick={() => trocarLista(true)}>Concluídas</button>
          </div>
        }
      />
      {notice && <Notice message={notice.text} kind={notice.kind} />}
      <div className="grid grid--stats history-stats">
        <Stat label="Presença no mês" value={`${stats.taxa_presenca}%`} />
        <Stat label="Registros concluídos" value={stats.total_aulas} tone="green" />
        <Stat
          label="Maior alerta de faltas"
          value={stats.alunos_faltosos[0]?.faltas ?? 0}
          detail={stats.alunos_faltosos[0]?.nome ?? "Nenhum alerta"}
          tone="rose"
        />
      </div>
      <Card className="history-panel">
        <div className="card__header history-panel__header">
          <div>
            <h2>{finalizadas ? "Chamadas concluídas" : "Aguardando chamada"}</h2>
            <p>{finalizadas ? "Abra uma aula para consultar ou corrigir a chamada." : "Uma linha representa uma aula completa, inclusive as turmas."}</p>
          </div>
          <Badge tone={finalizadas ? "green" : "orange"}>{filtradas.length} aula(s)</Badge>
        </div>
        <div className="card__body">
          <div className="toolbar">
            <div className="search-wrap">
              <Search size={17} />
              <input
                className="search-input"
                placeholder="Buscar aluno, turma, professor ou data..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
          {loading ? <Loading /> : filtradas.length === 0 ? (
            <Empty text={finalizadas ? "Nenhuma chamada concluída encontrada." : "Nenhuma chamada pendente."} />
          ) : (
            <div className="table-wrap">
              <table className="history-table">
                <thead><tr><th>Data</th><th>Aula / turma</th><th>Professor</th><th>Alunos</th><th>Status</th><th>Ação</th></tr></thead>
                <tbody>
                  {filtradas.map((sessao) => (
                    <tr key={`${sessao.data}-${sessao.turma_id ?? sessao.alunos[0]?.historico_id}`}>
                      <td className="history-date">{new Date(sessao.data).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</td>
                      <td><strong>{sessao.nome_exibicao}</strong><small>{sessao.is_turma ? "Turma" : "Individual"}</small></td>
                      <td>{sessao.professor_nome ?? "Não informado"}</td>
                      <td><span className="history-student-count">{sessao.alunos.length}</span> {sessao.alunos.map((aluno) => aluno.nome).join(", ")}</td>
                      <td><Badge tone={finalizadas ? "green" : "orange"}>{finalizadas ? "Concluída" : "Pendente"}</Badge></td>
                      <td>
                        <Button variant="secondary" onClick={() => setRegistro(sessao)}>
                          {finalizadas ? <Eye size={14} /> : <CheckCircle2 size={14} />}
                          {finalizadas ? "Ver chamada" : "Registrar"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={Boolean(registro)}
        title={finalizadas ? "Detalhes e correção da chamada" : "Registrar chamada"}
        description={registro ? `${registro.nome_exibicao} · ${new Date(registro.data).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}` : undefined}
        onClose={() => setRegistro(null)}
        wide
        footer={
          <>
            <Button variant="secondary" onClick={() => setRegistro(null)}>Cancelar</Button>
            <Button type="submit" form="form-retroativa" disabled={saving}>{saving ? "Salvando..." : finalizadas ? "Salvar correções" : "Concluir chamada"}</Button>
          </>
        }
      >
        {registro && (
          <form id="form-retroativa" className="attendance-editor" onSubmit={salvar}>
            {registro.alunos.map((aluno) => (
              <section className="attendance-editor__row" key={aluno.historico_id}>
                <div className="attendance-editor__student">
                  <strong>{aluno.nome}</strong>
                  <span>{registro.is_turma ? registro.nome_exibicao : "Aula individual"}</span>
                </div>
                <SelectField label="Presença" name={`status-${aluno.historico_id}`} defaultValue={finalizadas ? (aluno.status_presenca ? "presente" : "ausente") : "presente"}>
                  <option value="presente">Presente</option>
                  <option value="ausente">Ausente</option>
                </SelectField>
                <SelectField label="Desempenho" name={`desempenho-${aluno.historico_id}`} defaultValue={aluno.desempenho ?? "Bom"}>
                  <option>Excelente</option><option>Bom</option><option>Regular</option><option>Precisa melhorar</option>
                </SelectField>
                <label className="field attendance-editor__note">
                  <span>Observação</span>
                  <textarea name={`observacao-${aluno.historico_id}`} defaultValue={aluno.observacao ?? ""} placeholder="Conteúdo, evolução ou ponto de atenção..." />
                </label>
              </section>
            ))}
          </form>
        )}
      </Modal>
    </>
  );
}
