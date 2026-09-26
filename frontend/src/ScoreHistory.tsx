import { useEffect, useState } from "react";
import { api } from "./api";

export type ScoreRecord = {
  batch_id: string | null;
  id: number;
  student_id: number;
  student_name: string;
  seat_number: number;
  creator_name: string;
  kind: "positive" | "negative";
  score: number;
  reason: string;
  note: string;
  needs_reason: boolean;
  created_at: string;
};
export type ScorePage = {
  count: number;
  next: string | null;
  previous: string | null;
  total: number | null;
  results: ScoreRecord[];
};

export function ScoreHistory({
  endpoint,
  teacher = false,
}: {
  endpoint: string;
  teacher?: boolean;
}) {
  const [data, setData] = useState<ScorePage | null>(null);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<ScorePage>(
      `${endpoint}${endpoint.includes("?") ? "&" : "?"}page=${page}`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) {
          setData(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [endpoint, page, revision]);
  return (
    <section
      className="score-history"
      aria-label={teacher ? "分數紀錄" : "我的分數"}
    >
      <div className="page-title">
        <h2>{teacher ? "分數紀錄" : "我的分數"}</h2>
        <button
          className="text-button"
          disabled={loading}
          onClick={() => setRevision((x) => x + 1)}
        >
          更新分數紀錄
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">正在載入分數…</p>
      ) : (
        data && (
          <>
            {data.total !== null && (
              <p className="score-total">
                累積分數 <strong>{data.total}</strong>
              </p>
            )}
            <p className="muted small">
              共 {data.count} 筆 · 由新到舊 · 分數與可花費的點數分開計算
            </p>
            {data.results.length === 0 ? (
              <p className="muted">目前還沒有分數紀錄。</p>
            ) : (
              <ol className="score-list">
                {data.results.map((record) => (
                  <li key={record.id} className="score-record">
                    <div className="score-record-top">
                      <strong>
                        {record.kind === "positive" ? "加分" : "扣分"}{" "}
                        {record.score > 0 ? "+" : ""}
                        {record.score}
                      </strong>
                      {teacher && (
                        <span>
                          {record.seat_number} 號 · {record.student_name}
                        </span>
                      )}
                    </div>
                    <p>
                      {record.reason}
                      {record.needs_reason && (
                        <span className="badge">待補原因</span>
                      )}
                    </p>
                    {record.note && <p className="score-note">{record.note}</p>}
                    {teacher && record.batch_id && (
                      <p className="muted small">
                        同批記分 · {record.batch_id.slice(0, 8)}
                      </p>
                    )}
                    <p className="muted small">
                      {record.creator_name} ·{" "}
                      <time dateTime={record.created_at}>
                        {new Date(record.created_at).toLocaleString("zh-TW")}
                      </time>
                    </p>
                  </li>
                ))}
              </ol>
            )}
            <nav className="actions" aria-label="分數紀錄分頁">
              <button
                className="secondary"
                disabled={!data.previous}
                onClick={() => setPage((x) => x - 1)}
              >
                上一頁
              </button>
              <span>第 {page} 頁</span>
              <button
                className="secondary"
                disabled={!data.next}
                onClick={() => setPage((x) => x + 1)}
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
