import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { auth } from "./services/api";
import DashboardScreen from "./screens/DashboardScreen";
import LoginScreen from "./screens/LoginScreen";
import PortalScreen from "./screens/PortalScreen";

function Protected({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!auth.get()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route
        path="/painel"
        element={<Protected><DashboardScreen /></Protected>}
      />
      <Route path="/portal/:token" element={<PortalScreen />} />
      <Route path="/" element={<Navigate to={auth.get() ? "/painel" : "/login"} replace />} />
      <Route path="*" element={<Navigate to={auth.get() ? "/painel" : "/login"} replace />} />
    </Routes>
  );
}
