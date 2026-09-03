import { useState, type FormEvent } from "react";
import { LockKeyhole, UserRound } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { Notice } from "../components/ui";
import { auth, errorMessage, request } from "../services/api";

export default function LoginScreen() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (auth.get()) return <Navigate to="/painel" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await request<{ access_token: string }>(
        "/token",
        {
          method: "POST",
          body: JSON.stringify({ username, password }),
          headers: { "Content-Type": "application/json" },
        },
        false,
      );
      auth.set(result.access_token);
      navigate("/painel", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page one-school-login">
      <section className="login-card">
        <header className="login-brand-panel">
          <div className="login-brand-panel__circle" />
          <div className="login-logo">
            <img src="/static/logo.png" alt="One School" />
          </div>
          <h1><span>One</span> School</h1>
          <p>Acesso do professor</p>
        </header>

        <form className="legacy-login-form" onSubmit={submit}>
          {error && <Notice message={error} />}
          <label className="login-field">
            <span>Usuário</span>
            <div>
              <UserRound size={19} />
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                aria-label="Usuário"
                required
                autoFocus
              />
            </div>
          </label>
          <label className="login-field">
            <span>Senha secreta</span>
            <div>
              <LockKeyhole size={18} />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                aria-label="Senha"
                required
              />
            </div>
          </label>
          <button className="login-submit" type="submit" disabled={busy}>
            {busy ? "Entrando..." : "Entrar no painel"}
          </button>
        </form>
      </section>
    </main>
  );
}
