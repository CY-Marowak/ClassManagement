import { useEffect, useState, type FormEvent } from "react";
import { api, type Cohort, type Student } from "./api";
import { AnimalAvatar } from "./AnimalAvatar";
import { StudentManagementDialog } from "./StudentManagementDialog";
import { StudentAuditHistory } from "./StudentAuditHistory";

type ImportResult = {
  summary: { created: number; skipped: number; error: number };
  results: {
    line: number;
    status: "created" | "skipped" | "error";
    message: string;
  }[];
};
const statuses = { created: "新增", skipped: "略過", error: "待修正" };

export function StudentRoster({
  cohort,
  onBack,
}: {
  cohort: Cohort;
  onBack: () => void;
}) {
  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [managing, setManaging] = useState<{
    student: Student;
    mode: "edit" | "reset";
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);
  const endpoint = `/classes/${cohort.id}/students/`;
  const link = `${location.origin}${location.pathname}#student-login?class=${cohort.student_login_code}`;
  useEffect(() => {
    api<Student[]>(endpoint)
      .then(setStudents)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [endpoint]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await api<ImportResult>(endpoint, "POST", { text }));
      setStudents(await api<Student[]>(endpoint));
      setHistoryRevision((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "匯入失敗，請稍後重試。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="roster">
      <button className="text-button" onClick={onBack} disabled={busy}>
        ← 返回我的班級
      </button>
      <div className="page-title">
        <div>
          <p className="eyebrow">班級工作空間 / 學生名單</p>
          <h1>{cohort.name}</h1>
          <p className="muted">{students.length} 位學生 · 依座號排序</p>
        </div>
        <button
          className="secondary"
          aria-expanded={showHistory}
          onClick={() => setShowHistory(!showHistory)}
        >
          {showHistory ? "收起操作紀錄" : "操作紀錄"}
        </button>
      </div>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {showHistory && (
        <StudentAuditHistory key={historyRevision} cohortId={cohort.id} />
      )}
      {managing && (
        <StudentManagementDialog
          student={managing.student}
          mode={managing.mode}
          endpoint={endpoint}
          onCancel={() => setManaging(null)}
          onComplete={(saved, message) => {
            setStudents((old) =>
              old
                .map((student) => (student.id === saved.id ? saved : student))
                .sort((a, b) => a.seat_number - b.seat_number),
            );
            setNotice(message);
            setManaging(null);
            setHistoryRevision((n) => n + 1);
          }}
        />
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <section className="roster-panel">
        <h2>邀請學生登入</h2>
        <p>
          班級登入碼：
          <strong className="login-code">{cohort.student_login_code}</strong>
        </p>
        <p className="muted small">
          登入碼固定不變。學生以學號和密碼登入，首次密碼為學號，登入後必須修改。
        </p>
        <label>
          學生登入連結
          <input
            readOnly
            value={link}
            onFocus={(event) => event.target.select()}
          />
        </label>
        <button
          className="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(link);
              setCopied("已複製登入連結。");
            } catch {
              setCopied("請選取上方連結並複製。");
            }
          }}
        >
          複製登入連結
        </button>
        {copied && (
          <p aria-live="polite" className="small">
            {copied}
          </p>
        )}
      </section>
      <section className="roster-panel">
        <h2>貼上名單，建立學生</h2>
        <p className="muted small">
          從試算表複製「座號、姓名、學號」三欄，最多 200
          筆。相同資料會略過；衝突列出原因，不會覆寫既有資料。
        </p>
        <form onSubmit={submit}>
          <label>
            貼上學生名單
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={7}
              maxLength={100000}
              required
              placeholder={"座號\t姓名\t學號\n1\t王小明\t00001"}
            />
          </label>
          <div className="actions">
            <button
              className="primary"
              disabled={busy || loading || !text.trim()}
            >
              {busy ? "匯入中…" : "匯入名單"}
            </button>
          </div>
        </form>
        {result && (
          <>
            <p className="notice" role="status">
              新增 {result.summary.created} · 略過 {result.summary.skipped} ·
              待修正 {result.summary.error}
            </p>
            <details open={result.summary.error > 0}>
              <summary>逐行匯入結果</summary>
              <ul className="import-results">
                {result.results.map((row) => (
                  <li
                    key={row.line}
                    className={row.status === "error" ? "import-error" : ""}
                  >
                    <strong>
                      第 {row.line} 行 · {statuses[row.status]}
                    </strong>
                    <span>{row.message}</span>
                  </li>
                ))}
              </ul>
            </details>
          </>
        )}
      </section>
      <section className="roster-panel">
        <h2>學生名單</h2>
        <p className="muted small table-scroll-hint">
          名單可左右滑動，查看完整資料與管理操作。
        </p>
        {loading ? (
          <p role="status">正在載入名單…</p>
        ) : students.length ? (
          <div className="table-scroll">
            <table aria-label="學生名單">
              <thead>
                <tr>
                  <th>座號</th>
                  <th>姓名</th>
                  <th>學號</th>
                  <th>角色</th>
                  <th>管理</th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <tr key={student.id}>
                    <td>{student.seat_number}</td>
                    <td>{student.name}</td>
                    <td>{student.student_number}</td>
                    <td>
                      <AnimalAvatar animal={student.avatar} />
                    </td>
                    <td>
                      <div className="student-actions">
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => {
                            setNotice("");
                            setManaging({ student, mode: "edit" });
                          }}
                        >
                          修改資料
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={busy}
                          onClick={() => {
                            setNotice("");
                            setManaging({ student, mode: "reset" });
                          }}
                        >
                          重設密碼
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">尚未建立學生，貼上名單就能開始。</p>
        )}
      </section>
    </section>
  );
}
