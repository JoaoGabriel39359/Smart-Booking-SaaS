import { useSearchParams } from "react-router-dom";
import AppShell, { type TabId } from "../components/AppShell";
import AgendaScreen from "./AgendaScreen";
import AlunosScreen from "./AlunosScreen";
import FrequenciaScreen from "./FrequenciaScreen";
import GradeScreen from "./GradeScreen";
import HistoricoScreen from "./HistoricoScreen";
import ProfessoresScreen from "./ProfessoresScreen";
import TurmasScreen from "./TurmasScreen";

const validTabs: TabId[] = [
  "agenda",
  "historico",
  "frequencia",
  "professores",
  "alunos",
  "turmas",
  "grade",
];

export default function DashboardScreen() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("aba") as TabId | null;
  const active: TabId = requested && validTabs.includes(requested) ? requested : "agenda";

  function change(tab: TabId) {
    setParams(tab === "agenda" ? {} : { aba: tab }, { replace: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const screens: Record<TabId, React.ReactNode> = {
    agenda: <AgendaScreen />,
    historico: <HistoricoScreen />,
    frequencia: <FrequenciaScreen />,
    professores: <ProfessoresScreen />,
    alunos: <AlunosScreen />,
    turmas: <TurmasScreen />,
    grade: <GradeScreen />,
  };

  return (
    <AppShell active={active} onChange={change}>
      {screens[active]}
    </AppShell>
  );
}
