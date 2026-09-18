import { useEffect, useState } from "react";
import { api } from "./api";

type AuditEvent = {
  id: number;
  student_id: number;
  student_name: string;
  actor_name: string;
  action: "created" | "profile_updated" | "password_reset";
  created_at: string;
  before: Record<string, string | number>;
  after: Record<string, string | number>;
};
type EventPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: AuditEvent[];
};
const actions = {
  created: "建立學生",
  profile_updated: "修改資料",
  password_reset: "重設密碼",
};
const fields: Record<string, string> = {
  name: "姓名",
  seat_number: "座號",
  student_number: "學號",
};

export function StudentAuditHistory({ cohortId }: { cohortId: number }) {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<EventPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<EventPage>(`/classes/${cohortId}/student-events/?page=${page}`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [cohortId, page, revision]);
  return (
    <section className="roster-panel" aria-label="學生操作紀錄">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">僅導師可查看</p>
          <h2>操作紀錄</h2>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => {
            setPage(1);
            setRevision((n) => n + 1);
          }}
        >
          重新整理
        </button>
      </div>
      <p className="muted small">
        依時間由新到舊，顯示操作當時的姓名。密碼重設只記事件，不顯示密碼。
      </p>
      {loading ? (
        <p role="status">正在載入操作紀錄…</p>
      ) : error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : (
        data && (
          <>
            {data.results.length ? (
              <ol className="audit-events">
                {data.results.map((event) => (
                  <li key={event.id}>
                    <div className="audit-heading">
                      <h3>{actions[event.action]}</h3>
                      <time dateTime={event.created_at}>
                        {new Date(event.created_at).toLocaleString("zh-TW", {
                          hour12: false,
                        })}
                      </time>
                    </div>
                    <p>
                      <strong>{event.student_name}</strong>
                      <span className="muted">
                        {" "}
                        · 學生 #{event.student_id} ·{" "}
                        {event.actor_name || "未命名教師"}
                      </span>
                    </p>
                    {Object.keys(event.after).length > 0 && (
                      <dl className="audit-changes">
                        {Object.entries(event.after).map(([field, value]) => (
                          <div key={field}>
                            <dt>{fields[field] || field}</dt>
                            <dd>
                              {event.before[field]} → {value}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">尚無操作紀錄。</p>
            )}
            <div className="audit-pagination">
              <span className="small muted">
                共 {data.count} 筆 · 第 {page} 頁
              </span>
              <div className="actions">
                <button
                  className="secondary"
                  disabled={!data.previous}
                  onClick={() => setPage((n) => n - 1)}
                >
                  上一頁
                </button>
                <button
                  className="secondary"
                  disabled={!data.next}
                  onClick={() => setPage((n) => n + 1)}
                >
                  下一頁
                </button>
              </div>
            </div>
          </>
        )
      )}
    </section>
  );
}
