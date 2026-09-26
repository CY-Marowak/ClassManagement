import { useEffect, useState } from "react";
import { api } from "./api";

type Snapshot = Record<string, string | number | boolean | null>;
type Event = {
  id: number;
  actor_name: string;
  action: string;
  created_at: string;
  before: Snapshot;
  after: Snapshot;
};
type EventPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Event[];
};
const actions: Record<string, string> = {
  created: "建立記分",
  reason_filled: "補充原因",
  edited: "修改記分",
  deleted: "刪除記分",
};
const fields: Record<string, string> = {
  kind: "種類",
  score: "分數",
  reason: "原因模板",
  note: "補充原因",
  deleted_at: "刪除時間",
};
function value(field: string, item: Snapshot) {
  const v = item[field];
  if (v === undefined || v === null || v === "") return "—";
  if (field === "kind") return v === "positive" ? "加分" : "扣分";
  if (field === "deleted_at")
    return new Date(String(v)).toLocaleString("zh-TW");
  return String(v);
}
export function ScoreAuditHistory({ base }: { base: string }) {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<EventPage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<EventPage>(`${base}score-events/?page=${page}`)
      .then((r) => {
        if (active) setData(r);
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
  }, [base, page, revision]);
  return (
    <section className="roster-panel score-audit" aria-label="分數查核">
      <div className="panel-heading">
        <h2>分數查核</h2>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => {
            setPage(1);
            setRevision((v) => v + 1);
          }}
        >
          更新查核紀錄
        </button>
      </div>
      <p className="muted small">
        僅導師可查看。顯示操作當時的學生、原建立教師、操作者及前後差異，包含已刪除紀錄。
      </p>
      {loading ? (
        <p role="status">正在載入查核…</p>
      ) : error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : (
        data && (
          <>
            <ol className="audit-events">
              {data.results.map((event) => (
                <li key={event.id}>
                  <div className="audit-heading">
                    <h3>{actions[event.action] || event.action}</h3>
                    <time dateTime={event.created_at}>
                      {new Date(event.created_at).toLocaleString("zh-TW")}
                    </time>
                  </div>
                  <p>
                    <strong>
                      {event.after.seat_number} 號 · {event.after.student_name}
                    </strong>{" "}
                    · 操作者：{event.actor_name}
                  </p>
                  <p className="muted small">
                    原建立教師：{event.after.creator_name}
                  </p>
                  {event.action === "deleted" && (
                    <p>
                      原紀錄：{value("kind", event.before)}{" "}
                      {value("score", event.before)} 分 ·{" "}
                      {value("reason", event.before)}
                      {event.before.note ? ` · ${event.before.note}` : ""}
                      （已不計入總分）
                    </p>
                  )}
                  <dl className="audit-changes">
                    {Object.entries(fields)
                      .filter(([key]) => event.before[key] !== event.after[key])
                      .map(([key, label]) => (
                        <div key={key}>
                          <dt>{label}</dt>
                          <dd>
                            {value(key, event.before)} →{" "}
                            {value(key, event.after)}
                          </dd>
                        </div>
                      ))}
                  </dl>
                </li>
              ))}
            </ol>
            {!data.count && <p className="muted">尚無查核紀錄。</p>}
            <nav className="actions" aria-label="分數查核分頁">
              <button
                className="secondary"
                disabled={!data.previous}
                onClick={() => setPage((v) => v - 1)}
              >
                上一頁
              </button>
              <span>
                共 {data.count} 筆 · 第 {page} 頁
              </span>
              <button
                className="secondary"
                disabled={!data.next}
                onClick={() => setPage((v) => v + 1)}
              >
                下一頁
              </button>
            </nav>
          </>
        )
      )}
    </section>
  );
}
