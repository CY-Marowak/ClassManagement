import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Cohort } from "./api";
import { Announcements } from "./Announcements";
import { TeacherManagement } from "./TeacherManagement";

type Notification = {
  id: number;
  kind: string;
  title: string;
  cohort_name: string;
  created_at: string;
  viewed_at: string | null;
};
type Inbox = {
  results: Notification[];
  count: number;
  unread_count: number;
  latest_id: number;
  next: string | null;
  previous: string | null;
};
type Target = {
  cohort_id: number;
  announcement_id: number | null;
  member_id: number | null;
};
const labels: Record<string, string> = {
  announcement_published: "新公告",
  announcement_updated: "公告內容更新",
  announcement_comment: "公告新留言",
  pinned_comment: "置頂公告新留言",
  teacher_application: "教師申請",
};

export function Notifications({
  student = false,
  disabled = false,
}: {
  student?: boolean;
  disabled?: boolean;
}) {
  const [data, setData] = useState<Inbox | null>(null);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [target, setTarget] = useState<(Target & { cohort?: Cohort }) | null>(
    null,
  );
  const dialog = useRef<HTMLDialogElement>(null);
  const bell = useRef<HTMLButtonElement>(null);
  const loadVersion = useRef(0);
  const load = useCallback(async (number?: number) => {
    const version = ++loadVersion.current;
    try {
      const result = await api<Inbox>(
        number === undefined
          ? "/notifications/"
          : `/notifications/?page=${number}`,
      );
      if (version !== loadVersion.current) return;
      setData(result);
      setPage(number ?? 1);
    } catch (error) {
      if (version === loadVersion.current) throw error;
    }
  }, []);
  useEffect(() => {
    // Leave the initial count unknown on failure; opening the inbox retries.
    void load().catch(() => {});
    return () => {
      ++loadVersion.current;
    };
  }, [load]);
  useEffect(() => {
    if (!open) return;
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, [open]);
  async function refresh(number = 1) {
    setBusy(true);
    setError("");
    try {
      await load(number);
    } catch (e) {
      setError(e instanceof Error ? e.message : "無法讀取通知，請重試。");
    } finally {
      setBusy(false);
    }
  }
  function close() {
    setOpen(false);
    setTarget(null);
    bell.current?.focus();
  }
  async function openItem(item: Notification) {
    setBusy(true);
    setError("");
    try {
      const destination = await api<Target>(
        `/notifications/${item.id}/open/`,
        "POST",
      );
      const cohort = student
        ? undefined
        : await api<Cohort>(`/classes/${destination.cohort_id}/`);
      await load(1);
      setTarget({ ...destination, cohort });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "無法開啟通知，請重試或更新通知。",
      );
    } finally {
      setBusy(false);
    }
  }
  async function viewAll() {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      await api("/notifications/viewed/", "POST", {
        through_id: data.latest_id,
      });
      await load(page);
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新失敗，請重試。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        ref={bell}
        className="secondary notification-bell"
        disabled={disabled}
        aria-label={
          data ? `通知，${data.unread_count} 則未查看` : "通知，未讀數尚未載入"
        }
        onClick={() => {
          setOpen(true);
          setTarget(null);
          void refresh();
        }}
      >
        <svg
          aria-hidden="true"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
        </svg>{" "}
        通知 {data ? <span className="badge">{data.unread_count}</span> : "…"}
      </button>
      {open && (
        <dialog
          ref={dialog}
          className="notification-dialog"
          aria-label="通知中心"
          onCancel={(e) => {
            e.preventDefault();
            if (!busy) close();
          }}
        >
          <div className="page-title">
            <h2>通知中心</h2>
            <button className="text-button" disabled={busy} onClick={close}>
              關閉通知
            </button>
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {target ? (
            <>
              <button
                className="text-button"
                onClick={() => {
                  setTarget(null);
                  void refresh();
                }}
              >
                ← 返回通知列表
              </button>
              {target.announcement_id ? (
                <Announcements
                  key={target.announcement_id}
                  cohort={target.cohort}
                  initialAnnouncementId={target.announcement_id}
                />
              ) : (
                target.cohort && (
                  <TeacherManagement
                    cohort={target.cohort}
                    backLabel="← 返回通知列表"
                    onBack={() => {
                      setTarget(null);
                      void refresh();
                    }}
                  />
                )
              )}
            </>
          ) : (
            <>
              <p className="muted">
                {data ? `${data.unread_count} 則未查看` : "正在讀取通知…"} ·
                公告仍需手動確認已讀
              </p>
              <div className="actions">
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void refresh()}
                >
                  更新通知
                </button>
                <button
                  className="secondary"
                  disabled={busy || !data?.unread_count}
                  onClick={() => void viewAll()}
                >
                  全部已查看
                </button>
              </div>
              {busy && <p role="status">正在更新通知…</p>}
              <ul className="notification-list" aria-label="通知列表">
                {data?.results.map((item) => (
                  <li
                    key={item.id}
                    className={item.viewed_at ? "viewed" : "unviewed"}
                  >
                    <span className="badge">
                      {item.viewed_at ? "已查看" : "未查看"}
                    </span>
                    <button
                      className="notification-link"
                      disabled={busy}
                      onClick={() => void openItem(item)}
                    >
                      {labels[item.kind] || "通知"}：{item.title}
                    </button>
                    <p className="muted small">
                      {item.cohort_name} ·{" "}
                      {new Date(item.created_at).toLocaleString("zh-TW")}
                    </p>
                  </li>
                ))}
              </ul>
              {data?.count === 0 && <p className="muted">目前沒有通知。</p>}
              {data && data.count > 25 && (
                <nav className="actions" aria-label="通知分頁">
                  <button
                    className="secondary"
                    disabled={busy || !data.previous}
                    onClick={() => void refresh(page - 1)}
                  >
                    上一頁通知
                  </button>
                  <span>
                    第 {page} 頁 · 共 {data.count} 則
                  </span>
                  <button
                    className="secondary"
                    disabled={busy || !data.next}
                    onClick={() => void refresh(page + 1)}
                  >
                    下一頁通知
                  </button>
                </nav>
              )}
            </>
          )}
        </dialog>
      )}
    </>
  );
}
