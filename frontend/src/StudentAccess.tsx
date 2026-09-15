import { useEffect, useState, type FormEvent } from "react";
import { api, type StudentProfile, type StudentSession } from "./api";
import { AnimalAvatar } from "./AnimalAvatar";

export function StudentAccess({
  changing = false,
  route = "",
  onLogin,
  onLogout,
}: {
  changing?: boolean;
  route?: string;
  onLogin: (session: StudentSession) => void;
  onLogout: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    setError("");
    if (changing && data.password !== data.confirmation) {
      setError("兩次密碼不一致，請重新確認。");
      return;
    }
    setBusy(true);
    try {
      const result = await api<StudentSession>(
        changing ? "/student/change-password/" : "/student/login/",
        "POST",
        data,
      );
      onLogin(result);
      location.hash = "student";
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗，請再試一次。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="student-access">
      <section className="student-access-card">
        <p className="wordmark">
          <span className="brand-icon">CM</span> 班級日常
        </p>
        <p className="eyebrow">學生空間</p>
        <h1>{changing ? "設定自己的密碼" : "歡迎來到你的班級"}</h1>
        <p className="muted">
          {changing
            ? "首次登入，先設定只有你知道的密碼。至少 10 個字元，請避免學號、姓名、常見密碼或全數字。"
            : "輸入老師提供的班級登入碼、學號與密碼。首次密碼是你的學號。"}
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <form onSubmit={submit}>
          {!changing && (
            <>
              <label>
                班級登入碼
                <input
                  name="class_code"
                  defaultValue={
                    new URLSearchParams(route.split("?")[1]).get("class") || ""
                  }
                  required
                  minLength={10}
                  maxLength={10}
                  autoCapitalize="characters"
                  autoComplete="off"
                />
              </label>
              <label>
                學號
                <input
                  name="student_number"
                  required
                  maxLength={64}
                  autoComplete="username"
                  autoCapitalize="none"
                />
              </label>
            </>
          )}
          <label>
            {changing ? "新密碼" : "密碼"}
            <input
              name="password"
              type="password"
              required
              minLength={changing ? 10 : 1}
              maxLength={128}
              autoComplete={changing ? "new-password" : "current-password"}
            />
          </label>
          {changing && (
            <label>
              確認新密碼
              <input
                name="confirmation"
                type="password"
                required
                maxLength={128}
                autoComplete="new-password"
              />
            </label>
          )}
          <button className="primary full" disabled={busy}>
            {busy ? "處理中…" : changing ? "儲存密碼並進入班級" : "學生登入"}
          </button>
        </form>
        <nav className="account-links">
          {changing ? (
            <button
              className="text-button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api("/auth/logout/", "POST");
                  onLogout();
                } catch (e) {
                  setError(e instanceof Error ? e.message : "登出失敗。");
                } finally {
                  setBusy(false);
                }
              }}
            >
              登出
            </button>
          ) : (
            <a href="#login">教師登入</a>
          )}
        </nav>
      </section>
    </main>
  );
}

export function StudentHome({ onLogout }: { onLogout: () => void }) {
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<StudentProfile>("/student/me/")
      .then(setProfile)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <main className="student-access">
      <section className="student-access-card student-home">
        <div className="page-title">
          <p className="wordmark">
            <span className="brand-icon">CM</span> 班級日常
          </p>
          <button
            className="text-button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api("/auth/logout/", "POST");
                onLogout();
              } catch (e) {
                setError(e instanceof Error ? e.message : "登出失敗。");
              } finally {
                setBusy(false);
              }
            }}
          >
            登出
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {profile ? (
          <>
            <p className="eyebrow">我的班級</p>
            <p className="student-cohort">{profile.cohort.name}</p>
            <AnimalAvatar animal={profile.avatar} />
            <h1>{profile.name}</h1>
            <p className="badge">座號 {profile.seat_number}</p>
            <p className="muted">這是你的固定動物夥伴，一起開始班級日常。</p>
          </>
        ) : (
          !error && <p role="status">正在載入你的班級…</p>
        )}
      </section>
    </main>
  );
}
