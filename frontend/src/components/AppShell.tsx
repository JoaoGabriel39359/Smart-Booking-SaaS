import {
  BarChart3,
  CalendarDays,
  CalendarRange,
  GraduationCap,
  History,
  Layers3,
  LogOut,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import { auth } from "../services/api";

export type TabId =
  | "agenda"
  | "historico"
  | "frequencia"
  | "professores"
  | "alunos"
  | "turmas"
  | "grade";

const tabs: Array<{ id: TabId; label: string; icon: LucideIcon }> = [
  { id: "agenda", label: "Agenda", icon: CalendarDays },
  { id: "historico", label: "Histórico", icon: History },
  { id: "frequencia", label: "Frequência", icon: BarChart3 },
  { id: "professores", label: "Professores", icon: GraduationCap },
  { id: "alunos", label: "Alunos", icon: UsersRound },
  { id: "turmas", label: "Turmas", icon: Layers3 },
  { id: "grade", label: "Grade Base", icon: CalendarRange },
];

export default function AppShell({
  active,
  onChange,
  children,
}: {
  active: TabId;
  onChange: (tab: TabId) => void;
  children: React.ReactNode;
}) {
  function logout() {
    auth.clear();
    location.assign("/login");
  }

  return (
    <div className="app-layout one-school-layout">
      <div className="shell-container">
        <header className="topbar">
          <SchoolBrand />
          <nav className="top-tabs" aria-label="Navegação principal">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                className={active === id ? "active" : ""}
                onClick={() => onChange(id)}
                aria-current={active === id ? "page" : undefined}
                title={label}
              >
                <Icon size={15} strokeWidth={2.2} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </nav>
          <button className="logout-button" onClick={logout} title="Sair do painel">
            <LogOut size={16} />
            <span>Sair</span>
          </button>
        </header>
        <main className="workspace">{children}</main>
      </div>
    </div>
  );
}

function SchoolBrand() {
  return (
    <div className="school-brand">
      <div className="school-brand__logo">
        <img src="/static/logo.png" alt="One School" />
      </div>
      <div>
        <strong><span>One</span> School</strong>
        <small>Painel do professor</small>
      </div>
    </div>
  );
}
