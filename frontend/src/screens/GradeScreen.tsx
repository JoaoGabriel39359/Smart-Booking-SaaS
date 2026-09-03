import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { api, errorMessage, query } from "../services/api";
import type { Grade, Professor } from "../types";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Loading,
  Notice,
  SelectField,
} from "../components/ui";

const dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const diasCurtos = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"];

function indiceDia(data: Date) {
  return (data.getDay() + 6) % 7;
}

export default function GradeScreen() {
  const hoje = useMemo(() => new Date(), []);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [professores, setProfessores] = useState<Professor[]>([]);
  const [mesVisivel, setMesVisivel] = useState(new Date(hoje.getFullYear(), hoje.getMonth(), 1));
  const [diaSelecionado, setDiaSelecionado] = useState(hoje);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ text: string; kind: "error" | "success" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [turnos, profs] = await Promise.all([
        api.get<Grade[]>("/aulas/grade"),
        api.get<Professor[]>("/professores/"),
      ]);
      setGrades(turnos);
      setProfessores(profs);
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const celulasMes = useMemo(() => {
    const ano = mesVisivel.getFullYear();
    const mes = mesVisivel.getMonth();
    const quantidade = new Date(ano, mes + 1, 0).getDate();
    const vazioInicial = indiceDia(new Date(ano, mes, 1));
    return [
      ...Array.from({ length: vazioInicial }, () => null),
      ...Array.from({ length: quantidade }, (_, index) => new Date(ano, mes, index + 1)),
    ];
  }, [mesVisivel]);

  function mudarMes(delta: number) {
    const proximo = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth() + delta, 1);
    setMesVisivel(proximo);
    setDiaSelecionado(proximo);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post(query("/aulas/configurar-grade", {
        dia: indiceDia(diaSelecionado),
        inicio: String(form.get("inicio")),
        fim: String(form.get("fim")),
        professor_id: form.get("professor_id") ? Number(form.get("professor_id")) : null,
        capacidade: Number(form.get("capacidade") || 1),
      }));
      setNotice({ text: `Turno salvo para ${dias[indiceDia(diaSelecionado)]}.`, kind: "success" });
      event.currentTarget.reset();
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  async function remove(id: number) {
    if (!confirm("Remover este turno da grade?")) return;
    try {
      await api.delete(`/aulas/grade/${id}`);
      setNotice({ text: "Turno removido.", kind: "success" });
      await load();
    } catch (err) {
      setNotice({ text: errorMessage(err), kind: "error" });
    }
  }

  return (
    <>
      {notice && <Notice message={notice.text} kind={notice.kind} />}

      {loading ? <Card><Loading /></Card> : (
        <div className="grade-legacy-layout">
          <Card className="calendar-card">
            <div className="card__header calendar-card__header">
              <div>
                <h2><CalendarDays size={18} /> Calendário de Turnos</h2>
                <p>Clique em um dia para configurar a semana correspondente.</p>
              </div>
              <div className="month-controls">
                <button className="icon-button" onClick={() => mudarMes(-1)} aria-label="Mês anterior">
                  <ChevronLeft size={18} />
                </button>
                <strong>{mesVisivel.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}</strong>
                <button className="icon-button" onClick={() => mudarMes(1)} aria-label="Próximo mês">
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
            <div className="calendar-body">
              <div className="calendar-weekdays">
                {diasCurtos.map((dia) => <span key={dia}>{dia}</span>)}
              </div>
              <div className="calendar-grid">
                {celulasMes.map((data, index) => {
                  if (!data) return <div className="calendar-day calendar-day--empty" key={`vazio-${index}`} />;
                  const turnos = grades.filter((grade) => grade.ativo && grade.dia_semana === indiceDia(data));
                  const selecionado = data.toDateString() === diaSelecionado.toDateString();
                  const atual = data.toDateString() === hoje.toDateString();
                  return (
                    <button
                      className={`calendar-day ${selecionado ? "selected" : ""} ${atual ? "today" : ""}`}
                      key={data.toISOString()}
                      onClick={() => setDiaSelecionado(data)}
                    >
                      <span>{data.getDate()}</span>
                      {turnos.length > 0 && <small>{turnos.length} {turnos.length === 1 ? "turno" : "turnos"}</small>}
                    </button>
                  );
                })}
              </div>
            </div>
          </Card>

          <div className="grade-side">
            <Card className="grade-day-card">
              <div className="card__header">
                <div>
                  <h2>Configurar {dias[indiceDia(diaSelecionado)]}</h2>
                  <p>{diaSelecionado.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" })}</p>
                </div>
                <Badge tone="indigo">
                  {grades.filter((grade) => grade.dia_semana === indiceDia(diaSelecionado)).length} turnos
                </Badge>
              </div>
              <form className="grade-inline-form" onSubmit={save}>
                <div className="form-grid">
                  <Field label="Horário inicial" name="inicio" type="time" required />
                  <Field label="Horário final" name="fim" type="time" required />
                  <SelectField label="Professor" name="professor_id" defaultValue="">
                    <option value="">Sem professor</option>
                    {professores.filter((p) => p.ativo).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                  </SelectField>
                  <Field label="Vagas simultâneas" name="capacidade" type="number" min="1" max="10" defaultValue="1" required />
                </div>
                <Button type="submit"><Plus size={16} /> Salvar turno</Button>
              </form>

              <div className="selected-turns">
                {grades.filter((grade) => grade.dia_semana === indiceDia(diaSelecionado)).map((grade) => (
                  <article className="selected-turn" key={grade.id}>
                    <div>
                      <strong>{grade.hora_inicio} — {grade.hora_fim}</strong>
                      <span>{grade.nome_professor ?? "Sem professor"} · {grade.capacidade} vaga(s)</span>
                    </div>
                    <button className="icon-button" onClick={() => void remove(grade.id)} aria-label="Remover turno">
                      <Trash2 size={14} />
                    </button>
                  </article>
                ))}
              </div>
            </Card>

            <Card className="weekly-summary">
              <div className="card__header">
                <h2>Horários da semana</h2>
                <Badge tone="indigo">{grades.length} turnos</Badge>
              </div>
              <div className="weekly-summary__body">
                {grades.length === 0 ? <Empty text="Nenhum turno configurado." /> : dias.map((dia, indice) => {
                  const turnos = grades.filter((grade) => grade.dia_semana === indice);
                  if (turnos.length === 0) return null;
                  return (
                    <section className="weekly-row" key={dia}>
                      <strong>{dia}</strong>
                      <div>
                        {turnos.map((grade) => (
                          <span key={grade.id}>{grade.hora_inicio}–{grade.hora_fim}</span>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
