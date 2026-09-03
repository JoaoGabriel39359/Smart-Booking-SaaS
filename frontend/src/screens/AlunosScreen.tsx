import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  BarChart3,
  Clipboard,
  Edit3,
  ExternalLink,
  MessageCircle,
  Phone,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { api, errorMessage } from "../services/api";
import type { Aluno, RelatorioAluno, Turma, TipoAluno } from "../types";
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

export default function AlunosScreen() {
  const [alunos, setAlunos] = useState<Aluno[]>([]);
  const [turmas, setTurmas] = useState<Turma[]>([]);
  const [selected, setSelected] = useState<Aluno | null | undefined>(undefined);
  const [relatorio, setRelatorio] = useState<RelatorioAluno | null>(null);
  const [reportLoading, setReportLoading] = useState<number | null>(null);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [lista, listaTurmas] = await Promise.all([
        api.get<Aluno[]>("/alunos/"),
        api.get<Turma[]>("/turmas/"),
      ]);
      setAlunos(lista);
      setTurmas(listaTurmas);
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filtrados = useMemo(() => {
    const term = search.toLocaleLowerCase("pt-BR");
    return alunos.filter((aluno) =>
      `${aluno.nome} ${aluno.sobrenome} ${aluno.telefone} ${aluno.email ?? ""}`
        .toLocaleLowerCase("pt-BR").includes(term),
    );
  }, [alunos, search]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {
      nome: String(form.get("nome")),
      sobrenome: String(form.get("sobrenome")),
      telefone: String(form.get("telefone")),
      email: String(form.get("email")),
      tipo: String(form.get("tipo")) as TipoAluno,
      turma_id: form.get("turma_id") ? Number(form.get("turma_id")) : null,
      endereco: String(form.get("endereco") ?? "") || null,
      cidade: String(form.get("cidade") ?? "") || null,
      estado: String(form.get("estado") ?? "") || null,
    };
    if (selected) {
      payload.limite_aulas_semana = Number(form.get("limite_aulas_semana") || 1);
      payload.creditos_reposicao = Number(form.get("creditos_reposicao") || 0);
    }
    try {
      if (selected) await api.put(`/alunos/${selected.id}`, payload);
      else await api.post("/alunos/", payload);
      setSelected(undefined);
      setNotice({ text: "Aluno salvo com sucesso.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function remove(aluno: Aluno) {
    if (!confirm(`Excluir o cadastro de ${aluno.nome}? Esta ação não pode ser desfeita.`)) return;
    try {
      await api.delete(`/alunos/${aluno.id}`);
      setNotice({ text: "Aluno removido.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function portalLink(aluno: Aluno) {
    if (aluno.token_acesso) return `${location.origin}/portal/${aluno.token_acesso}`;
    const result = await api.get<{ link: string }>(`/alunos/${aluno.id}/link-portal`);
    return result.link;
  }

  async function copyPortal(aluno: Aluno) {
    try {
      await navigator.clipboard.writeText(await portalLink(aluno));
      setNotice({ text: "Link do portal copiado.", kind: "success" });
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function openPortal(aluno: Aluno) {
    try {
      window.open(await portalLink(aluno), "_blank", "noopener,noreferrer");
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function sendPortal(aluno: Aluno) {
    if (!confirm(`Enviar o link do portal para o WhatsApp de ${aluno.nome}?`)) return;
    setSendingId(aluno.id);
    try {
      await api.post(`/alunos/${aluno.id}/enviar-portal`);
      setNotice({ text: "Link enviado pelo WhatsApp.", kind: "success" });
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setSendingId(null);
    }
  }

  async function showReport(aluno: Aluno) {
    setReportLoading(aluno.id);
    try {
      setRelatorio(await api.get<RelatorioAluno>(`/alunos/${aluno.id}/relatorio`));
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setReportLoading(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Alunos"
        description="Cadastro, acesso ao portal e acompanhamento pedagógico."
        actions={<Button onClick={() => setSelected(null)}><Plus size={17} /> Novo aluno</Button>}
      />
      {notice && <Notice message={notice.text} kind={notice.kind} />}
      <Card className="students-panel">
        <div className="card__body">
          <div className="toolbar">
            <div className="search-wrap">
              <Search size={17} />
              <input
                className="search-input"
                placeholder="Buscar aluno, telefone ou e-mail..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
          {loading ? <Loading /> : filtrados.length === 0 ? <Empty /> : (
            <div className="students-grid">
              {filtrados.map((aluno) => (
                <article className="student-compact-card" key={aluno.id}>
                  <div className="student-identity">
                    <div className="student-name-row">
                      <strong>{aluno.nome} {aluno.sobrenome}</strong>
                      <Badge tone={aluno.tipo === "VIP" ? "green" : "indigo"}>{aluno.tipo}</Badge>
                    </div>
                    <span><Phone size={11} /> {aluno.telefone}</span>
                  </div>
                  <div className="student-actions">
                    <button type="button" className="student-icon-button student-icon-button--portal" title="Abrir portal" aria-label={`Abrir portal de ${aluno.nome}`} onClick={() => void openPortal(aluno)}><ExternalLink size={17} /></button>
                    <button type="button" className="student-icon-button student-icon-button--copy" title="Copiar link" aria-label={`Copiar link de ${aluno.nome}`} onClick={() => void copyPortal(aluno)}><Clipboard size={17} /></button>
                    <button type="button" className="student-icon-button student-icon-button--whatsapp" title="Enviar pelo WhatsApp" aria-label={`Enviar link para ${aluno.nome}`} disabled={sendingId === aluno.id} onClick={() => void sendPortal(aluno)}><MessageCircle size={17} /></button>
                    <button type="button" className="student-icon-button student-icon-button--report" title="Ver relatório detalhado" aria-label={`Ver relatório de ${aluno.nome}`} disabled={reportLoading === aluno.id} onClick={() => void showReport(aluno)}><BarChart3 size={17} /></button>
                    <button type="button" className="student-icon-button student-icon-button--edit" title="Editar" aria-label={`Editar ${aluno.nome}`} onClick={() => setSelected(aluno)}><Edit3 size={17} /></button>
                    <button type="button" className="student-icon-button student-icon-button--delete" title="Excluir" aria-label={`Excluir ${aluno.nome}`} onClick={() => void remove(aluno)}><Trash2 size={17} /></button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={selected !== undefined}
        title={selected ? "Editar aluno" : "Novo aluno"}
        description={selected ? "Alterações de crédito atualizam também sua origem real." : "Cadastre os dados básicos e o plano."}
        onClose={() => setSelected(undefined)}
        wide
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelected(undefined)}>Cancelar</Button>
            <Button type="submit" form="form-aluno">Salvar aluno</Button>
          </>
        }
      >
        <form id="form-aluno" className="form-grid" onSubmit={save}>
          <Field label="Nome" name="nome" defaultValue={selected?.nome ?? ""} required />
          <Field label="Sobrenome" name="sobrenome" defaultValue={selected?.sobrenome ?? ""} required />
          <Field label="WhatsApp" name="telefone" defaultValue={selected?.telefone ?? ""} required />
          <Field label="E-mail" name="email" type="email" defaultValue={selected?.email ?? ""} required />
          <SelectField label="Plano" name="tipo" defaultValue={selected?.tipo ?? "VIP"}>
            <option value="VIP">VIP</option><option value="DUO">DUO</option><option value="TEAM">TEAM</option>
          </SelectField>
          <SelectField label="Turma" name="turma_id" defaultValue={selected?.turma_id ?? ""}>
            <option value="">Sem turma</option>
            {turmas.map((turma) => <option key={turma.id} value={turma.id}>{turma.nome_turma}</option>)}
          </SelectField>
          {selected && (
            <>
              <Field label="Aulas por semana" name="limite_aulas_semana" type="number" min="1" max="10" defaultValue={selected.limite_aulas_semana ?? 2} />
              <Field label="Créditos de reposição" name="creditos_reposicao" type="number" min="0" defaultValue={selected.creditos_reposicao ?? 0} />
            </>
          )}
          <Field className="span-2" label="Endereço" name="endereco" defaultValue={selected?.endereco ?? ""} />
          <Field label="Cidade" name="cidade" defaultValue={selected?.cidade ?? ""} />
          <Field label="Estado" name="estado" maxLength={2} defaultValue={selected?.estado ?? ""} />
        </form>
      </Modal>

      <Modal
        open={Boolean(relatorio)}
        title={relatorio?.aluno.nome ?? "Relatório do aluno"}
        description={`${relatorio?.aluno.turma ?? "Sem turma"} · acompanhamento completo das aulas concluídas`}
        onClose={() => setRelatorio(null)}
        wide
        footer={<Button variant="secondary" onClick={() => setRelatorio(null)}>Fechar</Button>}
      >
        {relatorio && (
          <>
            <div className="student-report-summary">
              <div><span>Total de aulas</span><strong>{relatorio.resumo.total_aulas}</strong></div>
              <div><span>Presenças</span><strong className="text-success">{relatorio.resumo.presencas}</strong></div>
              <div><span>Faltas</span><strong className="text-danger">{relatorio.resumo.faltas}</strong></div>
              <div><span>Taxa de presença</span><strong>{relatorio.resumo.taxa_presenca}%</strong></div>
            </div>
            {relatorio.registros.length === 0 ? <Empty text="Nenhuma aula concluída para este aluno." /> : (
              <div className="table-wrap student-report-table">
                <table>
                  <thead><tr><th>Data</th><th>Aula</th><th>Professor</th><th>Presença</th><th>Desempenho</th><th>Observação</th></tr></thead>
                  <tbody>{relatorio.registros.map((item) => (
                    <tr key={`${item.id}-${item.data_inicio}`}>
                      <td>{new Date(item.data_inicio).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</td>
                      <td>{item.turma ?? "Individual"}{item.eh_reposicao && <Badge tone="orange">Reposição</Badge>}</td>
                      <td>{item.professor ?? "Não informado"}</td>
                      <td><Badge tone={item.presente ? "green" : "rose"}>{item.status}</Badge></td>
                      <td>{item.desempenho}</td>
                      <td className="report-observation">{item.observacao}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Modal>
    </>
  );
}
