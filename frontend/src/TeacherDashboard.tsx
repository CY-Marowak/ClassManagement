import { useEffect, useState } from "react";
import { api, type Cohort } from "./api";
import type { ScoreRecord } from "./ScoreHistory";

type Dashboard = {
  date: string;
  pending_teachers: number;
  pending_students: number;
  pending_reasons: number;
  today_scores: number;
  recent_scores: ScoreRecord[];
};
export type DashboardDestination =
  | "teachers"
  | "imports"
  | "pending"
  | "history"
  | "entry"
  | "awards"
  | "announcements"
  | "mascot";

export function TeacherDashboard({
  cohort,
  onBack,
  onOpen,
}: {
  cohort: Cohort;
  onBack: () => void;
  onOpen: (destination: DashboardDestination) => void;
}) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setData(null);
    api<Dashboard>(`/classes/${cohort.id}/dashboard/`)
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
  }, [cohort.id, revision]);
  return (
    <section>
      <button className="text-button" onClick={onBack}>
        ← 返回我的班級
      </button>
      <div className="page-title">
        <div>
          <p className="eyebrow">班級工作空間 / 工作首頁</p>
          <h1>{cohort.name}</h1>
          <p className="muted">先處理待辦，再開始今天的班級日常。</p>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => setRevision((n) => n + 1)}
        >
          重新整理首頁
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading && <p role="status">正在載入工作首頁…</p>}
      {data && (
        <>
          <div className="dashboard-grid" aria-label="班級待辦">
            <button
              className="dashboard-tile"
              onClick={() => onOpen("teachers")}
            >
              <span>待審教師</span>
              <strong>{data.pending_teachers}</strong>
              <small>前往教師管理 →</small>
            </button>
            <button
              className="dashboard-tile"
              onClick={() => onOpen("imports")}
            >
              <span>待修正學生</span>
              <strong>{data.pending_students}</strong>
              <small>處理匯入錯誤列 →</small>
            </button>
            <button
              className="dashboard-tile"
              onClick={() => onOpen("pending")}
            >
              <span>待補原因</span>
              <strong>{data.pending_reasons}</strong>
              <small>整理全班待補紀錄 →</small>
            </button>
            <div className="dashboard-tile">
              <span>今日記分</span>
              <strong>{data.today_scores}</strong>
              <small>{data.date} · 台北時間 · 有效紀錄</small>
            </div>
          </div>
          <div className="actions dashboard-actions">
            <button className="primary" onClick={() => onOpen("entry")}>
              開始記分
            </button>
            <button className="secondary" onClick={() => onOpen("awards")}>
              發點數
            </button>
            <button
              className="secondary"
              onClick={() => onOpen("announcements")}
            >
              班級公告
            </button>
            <button className="secondary" onClick={() => onOpen("mascot")}>
              班級吉祥物
            </button>
          </div>
          <section className="roster-panel" aria-label="最近十筆記分">
            <div className="page-title">
              <h2>最近十筆記分</h2>
              <button className="text-button" onClick={() => onOpen("history")}>
                查看全部分數紀錄 →
              </button>
            </div>
            <p className="muted small">
              全班有效紀錄，依建立時間由新到舊；修改後保留原排序。
            </p>
            {data.recent_scores.length === 0 && <p>目前還沒有記分紀錄。</p>}
            <ol className="dashboard-records">
              {data.recent_scores.map((record) => (
                <li key={record.id}>
                  <div>
                    <strong>
                      {record.seat_number} 號 · {record.student_name}
                    </strong>
                    <span className="badge">
                      {record.kind === "positive" ? "+" : ""}
                      {record.score} 分
                    </span>
                  </div>
                  <p>
                    {record.reason}
                    {record.note && ` · ${record.note}`}
                    {record.needs_reason && " · 待補原因"}
                    {record.is_modified && " · 已修改"}
                  </p>
                  <small className="muted">
                    {record.creator_name} ·{" "}
                    {new Date(record.created_at).toLocaleString("zh-TW", {
                      timeZone: "Asia/Taipei",
                    })}
                  </small>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </section>
  );
}
