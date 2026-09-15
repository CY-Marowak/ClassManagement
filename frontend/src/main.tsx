import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, type Identity } from "./api";
import { StudentAccess, StudentHome } from "./StudentAccess";
import { AccountForm } from "./AccountForm";
import { Classroom } from "./Classroom";
import "./style.css";

function App() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [route, setRoute] = useState(location.hash.slice(1) || "login");
  useEffect(() => {
    const changed = () => setRoute(location.hash.slice(1) || "login");
    window.addEventListener("hashchange", changed);
    api<Identity>("/auth/me/")
      .then(setIdentity)
      .catch(() => setIdentity(null))
      .finally(() => setLoading(false));
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  if (loading) return <main className="loading">正在準備你的班級空間…</main>;
  const studentLogout = () => {
    setIdentity(null);
    location.hash = "student-login";
  };
  if (identity?.account_type === "student") {
    return identity.must_change_password ? (
      <StudentAccess changing onLogin={setIdentity} onLogout={studentLogout} />
    ) : (
      <StudentHome onLogout={studentLogout} />
    );
  }
  if (!identity && route.split("?")[0] === "student-login") {
    return (
      <StudentAccess
        key={route}
        route={route}
        onLogin={setIdentity}
        onLogout={studentLogout}
      />
    );
  }
  const isActionLink =
    route.startsWith("verify?") || route.startsWith("reset?");
  return identity && !isActionLink ? (
    <Classroom
      teacher={identity}
      onLogout={() => {
        setIdentity(null);
        location.hash = "login";
      }}
      onRefresh={setIdentity}
    />
  ) : (
    <AccountForm
      key={route}
      route={route}
      onLogin={setIdentity}
      onPasswordReset={() => setIdentity(null)}
    />
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
