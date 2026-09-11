import { useEffect, useState, type FormEvent } from "react";
import { api, type Cohort, type Notice, type Teacher } from "./api";

function ClassForm({
  cohort,
  onSave,
  onCancel,
}: {
  cohort?: Cohort;
  onSave: (values: {
    name: string;
    entry_year: number;
    current_grade: number;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await onSave({
        name: String(data.get("name")),
        entry_year: Number(data.get("entry_year")),
        current_grade: Number(data.get("current_grade")),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "儲存失敗，請再試一次。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="class-form">
      <h3>{cohort ? "編輯班級資料" : "建立新班級"}</h3>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <label>
        班級名稱
        <input
          name="name"
          defaultValue={cohort?.name}
          placeholder="例如：向日葵班"
          required
          maxLength={80}
          autoFocus
        />
      </label>
      <div className="form-row">
        <label>
          入學年度
          <input
            name="entry_year"
            type="number"
            min={1900}
            max={2100}
            defaultValue={cohort?.entry_year ?? new Date().getFullYear()}
            required
          />
        </label>
        <label>
          目前年級
          <select
            name="current_grade"
            defaultValue={cohort?.current_grade ?? 1}
          >
            {Array.from({ length: 12 }, (_, i) => (
              <option key={i} value={i + 1}>
                {i + 1} 年級
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted small">
        班級會跟著同一屆學生延續。升上新年級時，更新這裡即可。
      </p>
      <div className="actions">
        <button
          className="secondary"
          type="button"
          onClick={onCancel}
          disabled={busy}
        >
          取消
        </button>
        <button className="primary" disabled={busy}>
          {busy ? "儲存中…" : cohort ? "儲存變更" : "建立班級"}
        </button>
      </div>
    </form>
  );
}

export function Classroom({
  teacher,
  onLogout,
  onRefresh,
}: {
  teacher: Teacher;
  onLogout: () => void;
  onRefresh: (teacher: Teacher) => void;
}) {
  const [classes, setClasses] = useState<Cohort[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Cohort | "new" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Cohort[]>("/classes/")
      .then(setClasses)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await run();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="wordmark" href="#classes">
          <span className="brand-icon">CM</span> 班級日常
        </a>
        <div className="side-menu">
          <p className="eyebrow">工作空間</p>
          <a className="active" href="#classes">
            ▦ <span>我的班級</span>
          </a>
        </div>
        <div className="profile">
          <span className="avatar">{teacher.display_name.slice(0, 1)}</span>
          <div>
            <strong>{teacher.display_name}</strong>
            <small>教師帳號</small>
          </div>
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              action(async () => {
                await api("/auth/logout/", "POST");
                onLogout();
              })
            }
          >
            登出
          </button>
        </div>
      </aside>
      <main className="workspace-main">
        <header>
          <p className="eyebrow">班級工作空間 / 我的班級</p>
          <div className="page-title">
            <div>
              <h1>我的班級</h1>
              <p className="muted">
                {teacher.display_name}，從這裡開始今天的班級日常。
              </p>
            </div>
            {teacher.email_verified && (
              <button className="primary" onClick={() => setEditing("new")}>
                ＋ 新增班級
              </button>
            )}
          </div>
        </header>
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="notice">
            {notice}
          </div>
        )}
        {!teacher.email_verified && (
          <section className="verification">
            <h2>再一步，完成 Email 驗證</h2>
            <p>請開啟信箱中的驗證連結。完成後，就能建立你的第一個班級。</p>
            <div className="actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const result = await api<Notice>(
                      "/auth/resend-verification/",
                      "POST",
                      { email: teacher.email },
                    );
                    setNotice(result.detail);
                  })
                }
              >
                重新寄送驗證信
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const current = await api<Teacher>("/auth/me/");
                    onRefresh(current);
                    if (!current.email_verified)
                      setNotice("尚未完成驗證，請先開啟信件連結。");
                  })
                }
              >
                我已驗證，重新確認
              </button>
            </div>
          </section>
        )}
        {editing && (
          <section className="editor">
            <ClassForm
              key={editing === "new" ? "new" : editing.id}
              cohort={editing === "new" ? undefined : editing}
              onCancel={() => setEditing(null)}
              onSave={async (values) => {
                const saved = await api<Cohort>(
                  editing === "new" ? "/classes/" : `/classes/${editing.id}/`,
                  editing === "new" ? "POST" : "PATCH",
                  values,
                );
                setClasses((old) =>
                  editing === "new"
                    ? [...old, saved]
                    : old.map((c) => (c.id === saved.id ? saved : c)),
                );
                setEditing(null);
                setNotice(
                  editing === "new"
                    ? "班級已建立，你是這個班級的導師。"
                    : "班級資料已更新。",
                );
              }}
            />
          </section>
        )}
        {loading ? (
          <p role="status">正在載入班級…</p>
        ) : classes.length ? (
          <section className="class-grid" aria-label="班級列表">
            {classes.map((c) => (
              <article className="class-card" key={c.id}>
                <div className="card-top">
                  <span className="class-symbol">▦</span>
                  <span className="badge">
                    {c.role === "homeroom" ? "導師" : "共同教師"}
                  </span>
                </div>
                <h2>{c.name}</h2>
                <p className="muted">
                  {c.entry_year} 年入學 · 同一屆，一起成長
                </p>
                <div className="card-bottom">
                  <span>
                    <strong>{c.current_grade}</strong> 年級
                  </span>
                  {c.role === "homeroom" && (
                    <button
                      className="text-button"
                      onClick={() => setEditing(c)}
                    >
                      編輯班級 →
                    </button>
                  )}
                </div>
              </article>
            ))}
          </section>
        ) : (
          !editing && (
            <section className="empty-state">
              <div className="empty-icon" aria-hidden="true">
                ▦
              </div>
              <h2>你的第一個班級，從這裡開始</h2>
              <p>
                取個名字、設定入學年度，
                <br />
                為你和學生建立一個共同的空間。
              </p>
              {teacher.email_verified && (
                <button className="primary" onClick={() => setEditing("new")}>
                  建立第一個班級
                </button>
              )}
            </section>
          )
        )}
        <footer>一個班級，一段持續成長的故事。</footer>
      </main>
    </div>
  );
}
