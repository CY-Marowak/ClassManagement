import { useEffect, useState } from "react";
import { api } from "./api";
import { membershipStatuses } from "./TeacherApplications";

type EventPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: {
    id: number;
    member_id: number | null;
    actor_name: string;
    teacher_name: string;
    action: string;
    created_at: string;
    before: { status?: string };
    after: { status?: string };
  }[];
};
const actions: Record<string, string> = {
  applied: "申請加入",
  approved: "批准加入",
  rejected: "拒絕申請",
  removed: "移除共同教師",
  code_rotated: "重產教師申請碼",
};

export function TeacherAuditHistory({ cohortId }: { cohortId: number }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EventPage | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    api<EventPage>(`/classes/${cohortId}/teacher-events/?page=${page}`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [cohortId, page]);
  return (
    <section className="roster-panel" aria-label="教師操作紀錄">
      <h2>教師操作紀錄</h2>
      <p className="muted small">依時間由新到舊，保留操作當時的姓名與狀態。</p>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : !data ? (
        <p role="status">正在載入紀錄…</p>
      ) : (
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
                    {event.teacher_name && (
                      <strong>
                        {event.teacher_name} · 成員 #{event.member_id} ·{" "}
                      </strong>
                    )}
                    操作者：{event.actor_name}
                  </p>
                  {event.after.status && (
                    <p>
                      {event.before.status
                        ? membershipStatuses[event.before.status]
                        : "尚未申請"}{" "}
                      → {membershipStatuses[event.after.status]}
                    </p>
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
      )}
    </section>
  );
}
