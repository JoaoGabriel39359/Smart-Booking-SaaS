import { useEffect, useMemo, useState } from "react";
import { CalendarX2, Clock3, MessageCircle, Search, Ticket } from "lucide-react";
import { api, errorMessage, query } from "../services/api";
import type { Cancelamento, Credito, Frequencia } from "../types";
import { Badge, Button, Card, Empty, Loading, Notice, PageHeader } from "../components/ui";

export default function FrequenciaScreen() {
  const [frequencia, setFrequencia] = useState<Frequencia[]>([]);
  const [cancelamentos, setCancelamentos] = useState<Cancelamento[]>([]);
  const [creditos, setCreditos] = useState<Credito[]>([]);
  const [periodo, setPeriodo] = useState(30);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [freq, canc, cred] = await Promise.all([
        api.get<Frequencia[]>(query("/relatorios/frequencia", { dias: periodo })),
        api.get<Cancelamento[]>("/relatorios/cancelamentos-semana"),
        api.get<Credito[]>("/relatorios/creditos"),
      ]);
      setFrequencia(freq);
      setCancelamentos(canc);
      setCreditos(cred);
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [periodo]);

  const filtrados = useMemo(() => {
    const term = search.toLocaleLowerCase("pt-BR");
    return frequencia.filter((item) => item.nome.toLocaleLowerCase("pt-BR").includes(term));
  }, [frequencia, search]);

  const creditosAtivos = creditos.reduce((sum, item) => sum + item.creditos_validos, 0);
  const totais = frequencia.reduce((acc, item) => ({
    aulas: acc.aulas + item.total_aulas,
    presencas: acc.presencas + item.presencas,
  }), { aulas: 0, presencas: 0 });
  const taxaGeral = totais.aulas ? Math.round((totais.presencas / totais.aulas) * 100) : 0;
  const alunosAtencao = frequencia.filter((item) => item.total_aulas > 0 && item.taxa_presenca < 75).length;

  async function enviarPortal(alunoId: number, nome: string) {
    if (!confirm(`Enviar o link do portal para ${nome} cobrar a reposição?`)) return;
    setSendingId(alunoId);
    try {
      await api.post(`/alunos/${alunoId}/enviar-portal`);
      setNotice({ text: "Link enviado pelo WhatsApp.", kind: "success" });
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setSendingId(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Relatório de Frequência & Créditos"
        description={`Acompanhamento pedagógico dos últimos ${periodo} dias e situação das reposições.`}
        actions={
          <label className="period-filter">
            <span>Período</span>
            <select value={periodo} onChange={(event) => setPeriodo(Number(event.target.value))}>
              <option value={30}>30 dias</option>
              <option value={60}>60 dias</option>
              <option value={90}>90 dias</option>
            </select>
          </label>
        }
      />
      {notice && <Notice message={notice.text} kind={notice.kind} />}

      <div className="frequency-layout">
        <Card className="frequency-main">
          <div className="card__header frequency-header">
            <div>
              <h2>Frequência dos alunos</h2>
              <p>{frequencia.length} aluno(s) com chamada concluída no período.</p>
            </div>
            <div className="frequency-header__tools">
              <div className="frequency-inline-summary">
                <span><strong>{taxaGeral}%</strong> presença geral</span>
                <span className={alunosAtencao ? "needs-attention" : ""}><strong>{alunosAtencao}</strong> em atenção</span>
              </div>
              <div className="search-wrap">
                <Search size={17} />
                <input className="search-input" placeholder="Buscar aluno..." value={search} onChange={(event) => setSearch(event.target.value)} />
              </div>
            </div>
          </div>
          <div className="card__body">
            {loading ? <Loading /> : filtrados.length === 0 ? <Empty text="Nenhuma chamada concluída neste período." /> : (
              <div className="table-wrap">
                <table className="frequency-table">
                  <thead><tr><th>Aluno</th><th>Total aulas</th><th>Presenças</th><th>Faltas</th><th>Cancelamentos</th><th>Taxa de presença</th><th>Última aula</th></tr></thead>
                  <tbody>
                    {filtrados.map((item) => (
                      <tr key={item.aluno_id}>
                        <td><strong>{item.nome}</strong></td>
                        <td>{item.total_aulas}</td>
                        <td><strong className="frequency-positive">{item.presencas}</strong></td>
                        <td><strong className="frequency-negative">{item.faltas}</strong></td>
                        <td><strong className="frequency-warning">{item.cancelamentos}</strong></td>
                        <td><Badge tone={item.taxa_presenca >= 75 ? "green" : item.taxa_presenca >= 50 ? "orange" : "rose"}>{item.taxa_presenca}%</Badge></td>
                        <td>{item.ultima_aula}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>

        <div className="frequency-bottom">
          <Card className="frequency-cancellations">
            <div className="card__header">
              <div><h3><CalendarX2 size={17} /> Cancelamentos recentes</h3><p>Cancelados nos últimos 7 dias.</p></div>
              <Badge tone="orange">{cancelamentos.length}</Badge>
            </div>
            <div className="card__body frequency-list-wrap">
              {loading ? <Loading /> : cancelamentos.length === 0 ? <Empty text="Nenhum cancelamento nos últimos 7 dias." /> : (
                <div className="frequency-list">
                  {cancelamentos.map((item) => (
                    <article className="frequency-list-item frequency-list-item--cancel" key={item.aula_id}>
                      <div>
                        <strong>{item.nome}</strong>
                        <span><Clock3 size={12} /> Aula: {item.data_aula}</span>
                      </div>
                      <Badge tone={item.gerou_credito && !item.credito_consumido ? "green" : "neutral"}>
                        {item.gerou_credito
                          ? item.credito_consumido
                            ? "Crédito consumido"
                            : item.validade_reposicao
                              ? `Crédito até ${item.validade_reposicao}`
                              : item.situacao_credito
                          : "Sem crédito"}
                      </Badge>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card className="frequency-credits">
            <div className="card__header">
              <div><h3><Ticket size={17} /> Créditos de reposição pendentes</h3><p>Ordenados pela validade mais próxima.</p></div>
              <Badge tone="green">{creditosAtivos} ativo(s)</Badge>
            </div>
            <div className="card__body frequency-list-wrap">
              {loading ? <Loading /> : creditos.length === 0 ? <Empty text="Nenhum crédito ativo." /> : (
                <div className="frequency-list">
                  {creditos.map((item) => (
                    <article className="frequency-list-item frequency-list-item--credit" key={item.aluno_id}>
                      <div>
                        <strong>{item.nome}</strong>
                        <span><Ticket size={12} /> {item.creditos_validos} crédito(s) · vence primeiro em {item.validade_proxima}</span>
                      </div>
                      <Button variant="secondary" disabled={sendingId === item.aluno_id} onClick={() => void enviarPortal(item.aluno_id, item.nome)}>
                        <MessageCircle size={14} /> {sendingId === item.aluno_id ? "Enviando..." : "Cobrar reposição"}
                      </Button>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
