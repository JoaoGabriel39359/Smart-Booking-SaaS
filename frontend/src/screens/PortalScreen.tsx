import { useEffect, useMemo, useState } from "react";
import { CalendarCheck2, Clock3, GraduationCap, XCircle } from "lucide-react";
import { useParams } from "react-router-dom";
import { api, errorMessage, query, request } from "../services/api";
import type { PortalData, Slot } from "../types";
import { Badge, Button, Empty, Loading, Notice } from "../components/ui";

export default function PortalScreen() {
  const { token = "" } = useParams();
  const [data, setData] = useState<PortalData | null>(null);
  const [dia, setDia] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [loading, setLoading] = useState(true);
  const [buscando, setBuscando] = useState(false);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" | "info" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      setData(await api.get<PortalData>(`/api/portal/${token}`, false));
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [token]);

  const dataMinima = useMemo(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().slice(0, 10);
  }, []);

  async function buscar() {
    if (!dia) return;
    setBuscando(true);
    setSlot(null);
    try {
      const [ano, mes, day] = dia.split("-");
      const response = await api.get<{ horarios_livres: Slot[] }>(
        query("/aulas/horarios-livres", { data: `${day}-${mes}-${ano}`, token }),
        false,
      );
      setSlots(response.horarios_livres);
      if (!response.horarios_livres.length) {
        setNotice({ text: "Não há vagas compatíveis com a duração da sua aula nesta data.", kind: "info" });
      }
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setBuscando(false);
    }
  }

  async function reagendar() {
    if (!dia || !slot) return;
    const form = new FormData();
    form.set("aula_id", "0");
    form.set("nova_data", `${dia}T${slot.hora}`);
    form.set("grade_id", String(slot.grade_id));
    try {
      await request(
        `/reagendar/${token}`,
        { method: "POST", body: form, headers: { Accept: "application/json" } },
        false,
      );
      setNotice({ text: "Reposição confirmada. O professor será informado.", kind: "success" });
      setSlots([]);
      setSlot(null);
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
      await buscar();
    }
  }

  async function cancelar(aulaId: number) {
    if (!confirm("Cancelar esta aula? Cancelamentos com pelo menos 3 horas geram crédito.")) return;
    try {
      await api.post(`/aulas/${aulaId}/cancelar/${token}`, undefined, false);
      setNotice({ text: "Aula cancelada. Seu saldo foi atualizado.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  if (loading) return <main className="portal-page"><div className="portal-shell"><Loading label="Abrindo seu portal..." /></div></main>;
  if (!data) return <main className="portal-page"><div className="portal-shell">{notice && <Notice message={notice.text} />}</div></main>;

  return (
    <main className="portal-page legacy-portal">
      <header className="portal-header">
        <div className="portal-header__circle" />
        <img src="/static/logo.png" alt="One School" />
        <h1>Olá, {data.aluno.nome}!</h1>
        <p>Painel de controle de aprendizado</p>
      </header>

      <div className="portal-shell">
        <div className="portal-account-row">
          <p>{data.aluno.tipo === "VIP" ? "Portal do Aluno VIP" : "Agenda de Aulas"}</p>
          {data.aluno.tipo === "VIP" && (
            <div className="portal-credit-card">
              <span>Créditos de reposição</span>
              <strong>{data.aluno.creditos_reposicao}</strong>
            </div>
          )}
        </div>

        {notice && <Notice message={notice.text} kind={notice.kind} />}

        <section className="portal-section">
          <h2><CalendarCheck2 size={20} /> Próximas Aulas</h2>
          {data.aulas.length === 0 ? <Empty text="Nenhuma aula encontrada." /> : (
            <div className="portal-lessons">
              {data.aulas.map((aula) => {
                const date = new Date(aula.data_inicio);
                return (
                  <article className="portal-lesson" key={aula.id}>
                    <div className="portal-lesson__date">
                      <strong>{date.toLocaleDateString("pt-BR", { day: "2-digit" })}</strong>
                      <span>{date.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "")}</span>
                    </div>
                    <div className="portal-lesson__info">
                      <strong>{date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</strong>
                      <Badge tone={aula.eh_reposicao ? "rose" : "indigo"}>
                        {aula.eh_reposicao ? "Reposição" : "Confirmada"}
                      </Badge>
                      {aula.professor_nome && <small>{aula.professor_nome}</small>}
                    </div>
                    {data.aluno.tipo === "VIP" && (
                      <button className="portal-cancel" onClick={() => void cancelar(aula.id)} title="Cancelar aula">
                        <XCircle size={24} />
                      </button>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </section>

        {data.aluno.tipo === "VIP" && (
          <section className="portal-section portal-replacement">
            <h2><Clock3 size={20} /> Agendar Reposição</h2>
            <div className="portal-replacement-card">
              {data.aluno.creditos_reposicao <= 0 ? (
                <Empty text="Você não possui créditos válidos no momento." />
              ) : (
                <>
                  <label className="field">
                    <span>1. Escolha uma data</span>
                    <input type="date" min={dataMinima} value={dia} onChange={(e) => { setDia(e.target.value); setSlots([]); setSlot(null); }} />
                  </label>
                  <Button className="portal-search-button" variant="secondary" onClick={() => void buscar()} disabled={!dia || buscando}>
                    <CalendarCheck2 size={16} /> {buscando ? "Consultando..." : "Buscar horários"}
                  </Button>
                  {slots.length > 0 && (
                    <>
                      <div className="slot-grid">
                        {slots.map((item) => (
                          <button
                            className={`slot ${slot?.grade_id === item.grade_id && slot?.hora === item.hora ? "active" : ""}`}
                            key={`${item.hora}-${item.grade_id}`}
                            onClick={() => setSlot(item)}
                          >
                            {item.hora}<br /><small>{item.vagas} vaga(s)</small>
                          </button>
                        ))}
                      </div>
                      <Button className="portal-confirm-button" onClick={() => void reagendar()} disabled={!slot}>
                        <GraduationCap size={16} /> Confirmar nova aula
                      </Button>
                    </>
                  )}
                </>
              )}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
