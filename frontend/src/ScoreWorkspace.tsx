import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Cohort } from "./api";
import { ScoreHistory, type ScoreRecord } from "./ScoreHistory";

type Kind = "positive" | "negative";
type ScoreRoster = {
  students: { id: number; name: string; seat_number: number; total: number }[];
  templates: Record<Kind, Record<string, string>>;
};

export function ScoreWorkspace({
  cohort,
  onBack,
}: {
  cohort: Cohort;
  onBack: () => void;
}) {
  const [roster, setRoster] = useState<ScoreRoster | null>(null);
  const [studentId, setStudentId] = useState("");
  const [kind, setKind] = useState<Kind>("positive");
  const [score, setScore] = useState("1");
  const [template, setTemplate] = useState("participation");
  const [note, setNote] = useState("");
  const [filter, setFilter] = useState("");
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requests = useRef(new Map<string, string>());
  const submitting = useRef(false);
  const base = `/classes/${cohort.id}/`;
  useEffect(() => {
    let active = true;
    setLoading(true);
    api<ScoreRoster>(base + "score-roster/")
      .then((result) => {
        if (active) setRoster(result);
      })
      .catch((e) => {
        if (active) {
          setRoster(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [base, revision]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const value = Number(score);
    if (!Number.isInteger(value) || score.trim() === "") {
      setError("請輸入整數分數。");
      return;
    }
    const payload = {
      student_id: Number(studentId),
      kind,
      score: value,
      template,
      note: note.trim(),
    };
    const fingerprint = JSON.stringify(payload);
    const requestId = requests.current.get(fingerprint) || crypto.randomUUID();
    requests.current.set(fingerprint, requestId);
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await api<ScoreRecord>(base + "scores/", "POST", {
        ...payload,
        request_id: requestId,
      });
      requests.current.clear();
      setNotice(
        `已記錄 ${saved.student_name}：${saved.kind === "positive" ? "加分" : "扣分"} ${saved.score}。未發放點數。`,
      );
      setNote("");
      setRevision((x) => x + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "記分失敗，請重試。");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <button className="text-button" disabled={busy} onClick={onBack}>
        ← 返回我的班級
      </button>
      <header>
        <p className="eyebrow">{cohort.name} / 教學紀錄</p>
        <h1>記分與紀錄</h1>
        <p className="muted">
          記錄每一次表現。這裡只調整分數，獎勵點數另行發放。
        </p>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <button
        className="text-button"
        disabled={busy || loading}
        onClick={() => {
          setError("");
          setRevision((x) => x + 1);
        }}
      >
        重新整理名單與紀錄
      </button>
      {loading ? (
        <p role="status">正在載入名單…</p>
      ) : (
        roster && (
          <>
            {roster.students.length ? (
              <section className="editor" aria-label="單筆記分">
                <form onSubmit={submit} className="score-form">
                  <h2>新增一筆記分</h2>
                  <fieldset disabled={busy}>
                    <label>
                      記分學生
                      <select
                        aria-label="記分學生"
                        value={studentId}
                        required
                        onChange={(e) => setStudentId(e.target.value)}
                      >
                        <option value="">選擇學生（依座號）</option>
                        {roster.students.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.seat_number} 號 · {s.name}（總分 {s.total}）
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="form-row">
                      <label>
                        加扣分種類
                        <select
                          value={kind}
                          onChange={(e) => {
                            const next = e.target.value as Kind;
                            setKind(next);
                            setScore(next === "positive" ? "1" : "-1");
                            setTemplate(
                              next === "positive"
                                ? "participation"
                                : "disruption",
                            );
                          }}
                        >
                          <option value="positive">加分</option>
                          <option value="negative">扣分</option>
                        </select>
                      </label>
                      <label>
                        分數
                        <input
                          type="number"
                          value={score}
                          min={kind === "positive" ? 0 : -100}
                          max={kind === "positive" ? 100 : 0}
                          step={1}
                          required
                          onChange={(e) => setScore(e.target.value)}
                        />
                      </label>
                    </div>
                    <p className="muted small">
                      {kind === "positive" ? "加分 0～100" : "扣分 −100～0"}
                      ，只接受整數；0 分也會留下紀錄。
                    </p>
                    <label>
                      原因模板
                      <select
                        value={template}
                        onChange={(e) => setTemplate(e.target.value)}
                      >
                        {Object.entries(roster.templates[kind]).map(
                          ([id, label]) => (
                            <option key={id} value={id}>
                              {label}
                            </option>
                          ),
                        )}
                        <option value="other">其他</option>
                      </select>
                    </label>
                    <label>
                      補充原因（選填）
                      <textarea
                        value={note}
                        maxLength={1000}
                        rows={3}
                        onChange={(e) => setNote(e.target.value)}
                      />
                    </label>
                    {template === "other" && !note.trim() && (
                      <p className="muted small">
                        未填寫原因，這筆會標記「待補原因」，仍可送出。
                      </p>
                    )}
                    <button className="primary" disabled={busy || !studentId}>
                      {busy ? "記錄中…" : "送出記分"}
                    </button>
                  </fieldset>
                </form>
              </section>
            ) : (
              <p className="notice">班級目前沒有學生，請由導師先加入學生。</p>
            )}
            <label className="score-filter">
              查看紀錄
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="">全班學生</option>
                {roster.students.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.seat_number} 號 · {s.name}（總分 {s.total}）
                  </option>
                ))}
              </select>
            </label>
            <ScoreHistory
              key={`${filter}-${revision}`}
              teacher
              endpoint={`${base}scores/${filter ? `?student_id=${filter}` : ""}`}
            />
          </>
        )
      )}
    </>
  );
}
