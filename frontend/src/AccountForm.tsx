import { useState, type FormEvent } from "react";
import { api, type Notice, type Teacher } from "./api";

const titles: Record<string, string> = {
  login: "歡迎回到班級日常",
  register: "建立你的教師帳號",
  forgot: "找回你的帳號",
  verify: "驗證你的 Email",
  reset: "設定新的密碼",
  resend: "重新取得驗證信",
};
const hints: Record<string, string> = {
  login: "登入後，繼續照顧每一個成長的日常。",
  register: "從一個班級開始，讓每天的教學更有條理。",
  forgot: "輸入註冊時的 Email，我們會寄送密碼重設連結。",
  verify: "確認後，即可登入並建立你的第一個班級。",
  reset: "新密碼設定完成後，請重新登入。",
  resend: "輸入註冊 Email，取得新的驗證連結。",
};

export function AccountForm({
  route,
  onLogin,
  onPasswordReset,
}: {
  route: string;
  onLogin: (teacher: Teacher) => void;
  onPasswordReset: () => void;
}) {
  const [rawMode, query] = route.split("?");
  const mode = titles[rawMode] ? rawMode : "login";
  const token = new URLSearchParams(query).get("token");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (mode === "login") {
        onLogin(await api<Teacher>("/auth/login/", "POST", data));
        location.hash = "classes";
      } else {
        const endpoint = {
          register: "register",
          forgot: "forgot-password",
          resend: "resend-verification",
          verify: "verify",
          reset: "reset-password",
        }[mode];
        const result = await api<Notice>(`/auth/${endpoint}/`, "POST", {
          ...data,
          ...(token ? { token } : {}),
        });
        setNotice(result.detail);
        setDone(true);
        if (mode === "reset") onPasswordReset();
        if (token) history.replaceState(null, "", `#${mode}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作未完成，請再試一次。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-layout">
      <section className="brand-panel">
        <a className="wordmark" href="#login">
          <span className="brand-icon">CM</span> 班級日常
        </a>
        <div className="brand-story">
          <p className="eyebrow">A LITTLE CARE, EVERY DAY</p>
          <h1>
            一起照顧
            <br />
            每一天的成長。
          </h1>
          <p>
            把繁忙的班級事務整理好，
            <br />
            留更多心力給眼前的學生。
          </p>
          <div className="growth-art" aria-hidden="true">
            <span />
            <span />
            <span />
            <i />
          </div>
        </div>
        <p className="brand-foot">你的班級，你們共同的日常。</p>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <p className="eyebrow">教師工作空間</p>
          <h2>{titles[mode]}</h2>
          <p className="muted">{hints[mode]}</p>
          {notice && (
            <div className="notice" role="status">
              {notice}
            </div>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {!done && (
            <form onSubmit={submit}>
              {mode === "register" && (
                <label>
                  顯示名稱
                  <input
                    name="display_name"
                    autoComplete="name"
                    placeholder="例如：林老師"
                    maxLength={80}
                    required
                  />
                </label>
              )}
              {!["verify", "reset"].includes(mode) && (
                <label>
                  Email
                  <input
                    name="email"
                    type="email"
                    autoComplete="email"
                    placeholder="teacher@example.com"
                    required
                    maxLength={254}
                  />
                </label>
              )}
              {["login", "register", "reset"].includes(mode) && (
                <label>
                  {mode === "reset" ? "新密碼" : "密碼"}
                  <input
                    aria-label={mode === "reset" ? "新密碼" : "密碼"}
                    aria-describedby={
                      mode !== "login" ? "password-hint" : undefined
                    }
                    name="password"
                    type="password"
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                    minLength={mode === "login" ? 1 : 10}
                    maxLength={128}
                    required
                  />
                  {mode !== "login" && (
                    <small id="password-hint">
                      至少 10 個字元，避免常見密碼或只有數字。
                    </small>
                  )}
                </label>
              )}
              {["verify", "reset"].includes(mode) && !token ? (
                <p className="error">請從信件中的完整連結開啟此頁面。</p>
              ) : (
                <button className="primary full" disabled={busy}>
                  {busy
                    ? "處理中…"
                    : {
                        login: "登入班級日常",
                        register: "建立帳號並寄送驗證信",
                        forgot: "寄送重設連結",
                        resend: "寄送驗證信",
                        verify: "確認驗證 Email",
                        reset: "更新密碼",
                      }[mode]}
                </button>
              )}
            </form>
          )}
          <nav className="account-links">
            {mode === "login" ? (
              <>
                <a href="#forgot">忘記密碼？</a>
                <a href="#register">建立教師帳號 →</a>
              </>
            ) : (
              <a href="#login">← 返回登入</a>
            )}
            {["verify", "register"].includes(mode) && (
              <a href="#resend">重新寄送驗證信</a>
            )}
          </nav>
          <p className="privacy-note">你的 Email 不會公開給其他班級成員。</p>
        </div>
      </section>
    </main>
  );
}
