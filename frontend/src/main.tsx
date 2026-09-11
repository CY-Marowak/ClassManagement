import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, type Teacher } from "./api";
import { AccountForm } from "./AccountForm";
import { Classroom } from "./Classroom";
import "./style.css";

function App() {
  const [teacher, setTeacher] = useState<Teacher | null>(null);
  const [loading, setLoading] = useState(true);
  const [route, setRoute] = useState(location.hash.slice(1) || "login");
  useEffect(() => {
    const changed = () => setRoute(location.hash.slice(1) || "login");
    window.addEventListener("hashchange", changed);
    api<Teacher>("/auth/me/")
      .then(setTeacher)
      .catch(() => setTeacher(null))
      .finally(() => setLoading(false));
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  if (loading) return <main className="loading">正在準備你的班級空間…</main>;
  const isActionLink =
    route.startsWith("verify?") || route.startsWith("reset?");
  return teacher && !isActionLink ? (
    <Classroom
      teacher={teacher}
      onLogout={() => {
        setTeacher(null);
        location.hash = "login";
      }}
      onRefresh={setTeacher}
    />
  ) : (
    <AccountForm key={route} route={route} onLogin={setTeacher} />
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
