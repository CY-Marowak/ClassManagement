import { useRef, useState } from "react";
import { api, ApiError } from "./api";
import { AnnouncementReminders } from "./AnnouncementReminders";

type Confirmation = { content_version: number; confirmed_at: string | null };
type Reader = {
  id: number;
  seat_number: number;
  name: string;
  confirmed_at: string | null;
};
type Roster = {
  content_version: number;
  read_count: number;
  unread_count: number;
  students: Reader[];
};

export function StudentReadConfirmation({
  id,
  version,
  confirmedAt,
  onRefresh,
}: {
  id: number;
  version: number;
  confirmedAt: string | null;
  onRefresh: () => void;
}) {
  const [confirmed, setConfirmed] = useState(confirmedAt);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const pending = useRef(false);
  async function confirm() {
    if (pending.current || confirmed || stale) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await api<Confirmation>(
        `/student/announcements/${id}/read/`,
        "POST",
        { content_version: version },
      );
      setConfirmed(result.confirmed_at);
    } catch (e) {
      setStale(
        e instanceof ApiError && [403, 404, 409].includes(e.status ?? 0),
      );
      setError(
        e instanceof Error ? e.message : "確認結果不明，請重試確認已讀。",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="announcement-reading">
      <p className="small">
        {confirmed
          ? `已確認已讀 · ${new Date(confirmed).toLocaleString("zh-TW")}`
          : "尚未確認已讀"}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!confirmed && (
        <button
          className="secondary"
          disabled={busy || stale}
          onClick={confirm}
        >
          {busy ? "正在確認…" : "確認已讀"}
        </button>
      )}
      {stale && (
        <button className="text-button" onClick={onRefresh}>
          載入最新公告
        </button>
      )}
    </div>
  );
}

export function AnnouncementReadRoster({
  endpoint,
  version,
  disabled,
  onRefresh,
}: {
  endpoint: string;
  version: number;
  disabled: boolean;
  onRefresh: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Roster | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [filter, setFilter] = useState("all");
  const [reminderLocked, setReminderLocked] = useState(false);
  async function load() {
    setBusy(true);
    setData(null);
    setError("");
    setStale(false);
    try {
      const result = await api<Roster>(`${endpoint}read-receipts/`);
      if (result.content_version !== version) {
        setStale(true);
        setError("公告內容已更新，請載入最新公告後查看名單。");
      } else setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "無法讀取已讀名單。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="announcement-reading">
      <button
        className="text-button"
        disabled={disabled || busy || reminderLocked}
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          if (!open) void load();
        }}
      >
        {open ? "收合已讀名單" : "已讀／未讀名單"}
      </button>
      {open && (
        <section aria-label="目前版本已讀名單">
          {busy && <p role="status">正在載入已讀名單…</p>}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {stale ? (
            <button className="secondary" onClick={onRefresh}>
              載入最新公告
            </button>
          ) : (
            <button
              className="text-button"
              disabled={disabled || busy || reminderLocked}
              onClick={load}
            >
              更新已讀名單
            </button>
          )}
          {data && (
            <>
              <p>
                目前版本 · 已讀 {data.read_count} 人 · 未讀 {data.unread_count}{" "}
                人
              </p>
              <label>
                已讀狀態
                <select
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                >
                  <option value="all">全部學生</option>
                  <option value="read">已讀</option>
                  <option value="unread">未讀</option>
                </select>
              </label>
              <ul aria-label="公告閱讀名單" className="announcement-readers">
                {data.students
                  .filter(
                    (student) =>
                      filter === "all" ||
                      (filter === "read"
                        ? !!student.confirmed_at
                        : !student.confirmed_at),
                  )
                  .map((student) => (
                    <li key={student.id}>
                      <span>
                        {student.seat_number} 號 · {student.name}
                      </span>
                      <span className="muted small">
                        {student.confirmed_at
                          ? `已讀 · ${new Date(student.confirmed_at).toLocaleString("zh-TW")}`
                          : "未讀"}
                      </span>
                    </li>
                  ))}
              </ul>
              {!data.students.length && (
                <p className="muted">班級目前沒有學生。</p>
              )}
              <AnnouncementReminders
                endpoint={endpoint}
                version={version}
                students={data.students}
                disabled={disabled || busy}
                onLockChange={setReminderLocked}
                onRefresh={onRefresh}
              />
            </>
          )}
        </section>
      )}
    </div>
  );
}
