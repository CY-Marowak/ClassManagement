import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { createRequestId } from "./requestId";

type Reader = {
  id: number;
  seat_number: number;
  name: string;
  confirmed_at: string | null;
};
type Result = {
  sent: number;
  already_read: number;
  already_reminded: number;
  sent_date: string;
};
type History = {
  count: number;
  next: string | null;
  previous: string | null;
  results: {
    id: number;
    seat_number: number;
    name: string;
    actor_name: string;
    content_version: number;
    created_at: string;
  }[];
};
type Pending = {
  request_id: string;
  content_version: number;
  student_id?: number;
};

export function AnnouncementReminders({
  endpoint,
  version,
  students,
  disabled,
  onLockChange,
  onRefresh,
}: {
  endpoint: string;
  version: number;
  students: Reader[];
  disabled: boolean;
  onLockChange: (locked: boolean) => void;
  onRefresh: () => void;
}) {
  const [target, setTarget] = useState("all");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyError, setHistoryError] = useState("");
  const [historyBusy, setHistoryBusy] = useState(false);
  const pending = useRef<Pending | null>(null);
  const sending = useRef(false);
  const locked = busy || retry;
  useEffect(() => {
    onLockChange(locked);
    return () => onLockChange(false);
  }, [locked, onLockChange]);
  async function loadHistory(number = 1) {
    setHistoryBusy(true);
    setHistoryError("");
    try {
      setHistory(await api<History>(`${endpoint}reminders/?page=${number}`));
      setHistoryPage(number);
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : "無法讀取提醒紀錄。");
    } finally {
      setHistoryBusy(false);
    }
  }
  async function send() {
    if (sending.current || stale) return;
    if (!pending.current)
      pending.current = {
        request_id: createRequestId(),
        content_version: version,
        ...(target === "all" ? {} : { student_id: Number(target) }),
      };
    sending.current = true;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await api<Result>(
        `${endpoint}reminders/`,
        "POST",
        pending.current,
      );
      pending.current = null;
      setRetry(false);
      setResult(response);
      if (historyOpen) void loadHistory();
    } catch (e) {
      const definitive = e instanceof ApiError && e.status && e.status < 500;
      if (definitive) {
        pending.current = null;
        setRetry(false);
        setStale([403, 404, 409].includes(e.status!));
      } else setRetry(true);
      setError(
        e instanceof Error ? e.message : "發送結果不明，請重試這次提醒。",
      );
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  const unread = students.filter((student) => !student.confirmed_at);
  return (
    <section aria-label="手動未讀提醒" className="reminder-panel">
      <h3>提醒未讀學生</h3>
      <p className="muted small">
        手動發送站內通知。同公告每位學生依台北日期每日最多一次，改版不重置額度；發送時會略過已讀或今日已提醒者。
      </p>
      <label>
        提醒對象
        <select
          value={target}
          disabled={disabled || locked || stale}
          onChange={(e) => setTarget(e.target.value)}
        >
          <option value="all">全部目前符合資格的未讀學生</option>
          {unread.map((student) => (
            <option key={student.id} value={student.id}>
              {student.seat_number} 號 · {student.name}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {retry && (
        <p className="notice">
          尚未確認發送結果，已保留這次操作；請重試以確認結果。
        </p>
      )}
      <button
        className="secondary"
        disabled={
          disabled ||
          busy ||
          historyBusy ||
          stale ||
          (!retry && unread.length === 0)
        }
        onClick={() => void send()}
      >
        {busy ? "正在發送…" : retry ? "重試這次提醒" : "發送提醒"}
      </button>
      {stale && (
        <button className="text-button" onClick={onRefresh}>
          載入最新公告
        </button>
      )}
      {result && (
        <p role="status">
          已發送 {result.sent} 人；已讀略過 {result.already_read} 人；今日已提醒{" "}
          {result.already_reminded} 人（台北日期 {result.sent_date}）。
        </p>
      )}
      <div>
        <button
          className="text-button"
          disabled={locked || historyBusy}
          aria-expanded={historyOpen}
          onClick={() => {
            setHistoryOpen(!historyOpen);
            if (!historyOpen) void loadHistory();
          }}
        >
          {historyOpen ? "收合提醒紀錄" : "查看提醒紀錄"}
        </button>
      </div>
      {historyOpen && (
        <>
          {historyError && (
            <p role="alert" className="error">
              {historyError}
            </p>
          )}
          {historyBusy && <p role="status">正在載入提醒紀錄…</p>}
          <button
            className="text-button"
            disabled={locked || historyBusy}
            onClick={() => void loadHistory()}
          >
            更新提醒紀錄
          </button>
          <ul aria-label="已發提醒紀錄" className="announcement-readers">
            {history?.results.map((row) => (
              <li key={row.id}>
                <span>
                  {row.seat_number} 號 · {row.name}
                </span>
                <span className="muted small">
                  {new Date(row.created_at).toLocaleString("zh-TW", {
                    timeZone: "Asia/Taipei",
                  })}{" "}
                  · 第 {row.content_version} 版 · {row.actor_name}
                </span>
              </li>
            ))}
          </ul>
          {history?.count === 0 && <p className="muted">尚未發送提醒。</p>}
          {history && history.count > 25 && (
            <nav className="actions" aria-label="提醒紀錄分頁">
              <button
                disabled={locked || historyBusy || !history.previous}
                onClick={() => void loadHistory(historyPage - 1)}
              >
                上一頁提醒
              </button>
              <span>
                第 {historyPage} 頁 · 共 {history.count} 筆
              </span>
              <button
                disabled={locked || historyBusy || !history.next}
                onClick={() => void loadHistory(historyPage + 1)}
              >
                下一頁提醒
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
