import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError, type Cohort } from "./api";

type Issue = {
  id: number;
  batch_id: string;
  line: number;
  raw: string;
  message: string;
  status: "pending" | "resolved" | "ignored";
  revision: number;
  created_at: string;
};
type IssuePage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Issue[];
};

export function ImportIssues({
  cohort,
  onBack,
  backLabel = "← 返回我的班級",
}: {
  cohort: Cohort;
  onBack: () => void;
  backLabel?: string;
}) {
  const [data, setData] = useState<IssuePage | null>(null);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Issue | null>(null);
  const [ignoring, setIgnoring] = useState<Issue | null>(null);
  const [cells, setCells] = useState(["", "", ""]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const submitting = useRef(false);
  const base = `/classes/${cohort.id}/import-issues/`;
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setData(null);
    setEditing(null);
    setIgnoring(null);
    api<IssuePage>(`${base}?page=${page}`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) {
          if (e instanceof ApiError && e.status === 404 && page > 1) setPage(1);
          else setError(e.message);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [base, page, reload]);
  async function resolve(issue: Issue, action: "retry" | "ignore") {
    if (submitting.current || loading) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<Issue>(base + `${issue.id}/`, "POST", {
        action,
        revision: issue.revision,
        ...(action === "retry" ? { raw: cells.join("\t") } : {}),
      });
      if (result.status === "pending") {
        setEditing(result);
        setData((old) =>
          old
            ? {
                ...old,
                results: old.results.map((row) =>
                  row.id === result.id ? result : row,
                ),
              }
            : old,
        );
        setError(result.message);
      } else {
        setNotice(
          result.status === "ignored"
            ? "已忽略這列資料。"
            : "這列資料已完成，學生名單已確認。",
        );
        setReload((n) => n + 1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗，請重試。");
      if (e instanceof ApiError && [403, 404, 409].includes(e.status || 0)) {
        setEditing(null);
        setIgnoring(null);
        setData(null);
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <section>
      <button className="text-button" disabled={busy} onClick={onBack}>
        {backLabel}
      </button>
      <div className="page-title">
        <div>
          <p className="eyebrow">{cohort.name} / 匯入待辦</p>
          <h1>待修正學生</h1>
          <p className="muted">
            每列分別處理，完成後會從待辦移除。重新貼上名單不會自動結案舊錯誤。
          </p>
        </div>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={() => setReload((n) => n + 1)}
        >
          重新整理待修正名單
        </button>
      </div>
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
      {loading && <p role="status">正在載入待修正名單…</p>}
      {data && (
        <>
          <p>待處理 {data.count} 列</p>
          {data.count === 0 && (
            <div className="empty-state">
              <h2>沒有待修正資料</h2>
              <p>後續匯入遇到錯誤時，會保存到這裡。</p>
            </div>
          )}
          {data.results.map((issue) => (
            <article className="roster-panel import-issue" key={issue.id}>
              <h2>第 {issue.line} 行</h2>
              <p className="muted small">
                匯入時間：
                {new Date(issue.created_at).toLocaleString("zh-TW", {
                  timeZone: "Asia/Taipei",
                })}
              </p>
              <p className="import-raw">
                原始資料：{issue.raw.replaceAll("\t", " │ ")}
              </p>
              <p>{issue.message}</p>
              {editing?.id === issue.id ? (
                <form
                  onSubmit={(event: FormEvent) => {
                    event.preventDefault();
                    void resolve(editing, "retry");
                  }}
                >
                  <div className="dashboard-fields">
                    {["座號", "姓名", "學號"].map((label, index) => (
                      <label key={label}>
                        {label}
                        <input
                          required
                          disabled={busy}
                          value={cells[index]}
                          maxLength={[4, 80, 64][index]}
                          onChange={(event) =>
                            setCells((old) =>
                              old.map((value, i) =>
                                i === index ? event.target.value : value,
                              ),
                            )
                          }
                        />
                      </label>
                    ))}
                  </div>
                  <div className="actions">
                    <button className="primary" disabled={busy || loading}>
                      修正並重試
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => setEditing(null)}
                    >
                      取消修正
                    </button>
                  </div>
                </form>
              ) : ignoring?.id === issue.id ? (
                <div>
                  <p>確定忽略這列？將移出待辦，不會建立或更動學生。</p>
                  <div className="actions">
                    <button
                      className="danger"
                      disabled={busy || loading}
                      onClick={() => resolve(ignoring, "ignore")}
                    >
                      確認忽略
                    </button>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => setIgnoring(null)}
                    >
                      取消忽略
                    </button>
                  </div>
                </div>
              ) : (
                <div className="actions">
                  <button
                    className="secondary"
                    disabled={busy || loading}
                    onClick={() => {
                      setEditing(issue);
                      setIgnoring(null);
                      const parts = issue.raw.split("\t");
                      setCells(
                        parts.length <= 3
                          ? [parts[0] || "", parts[1] || "", parts[2] || ""]
                          : ["", "", ""],
                      );
                      setError("");
                    }}
                  >
                    修正這列
                  </button>
                  <button
                    className="text-button"
                    disabled={busy || loading}
                    onClick={() => {
                      setIgnoring(issue);
                      setEditing(null);
                    }}
                  >
                    忽略這列
                  </button>
                </div>
              )}
            </article>
          ))}
          <div className="actions">
            <button
              className="secondary"
              disabled={busy || !data.previous}
              onClick={() => setPage((p) => p - 1)}
            >
              上一頁
            </button>
            <span>第 {page} 頁</span>
            <button
              className="secondary"
              disabled={busy || !data.next}
              onClick={() => setPage((p) => p + 1)}
            >
              下一頁
            </button>
          </div>
        </>
      )}
    </section>
  );
}
