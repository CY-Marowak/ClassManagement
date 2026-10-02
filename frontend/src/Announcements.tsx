import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import type { JSONContent } from "@tiptap/react";
import { api, ApiError, type Cohort } from "./api";
import { AnnouncementContent, emptyDocument } from "./AnnouncementContent";
import { AnnouncementComments } from "./AnnouncementComments";
const AnnouncementEditor = lazy(() =>
  import("./AnnouncementEditor").then((module) => ({
    default: module.AnnouncementEditor,
  })),
);

type Announcement = {
  comment_count: number;
  id: number;
  title: string;
  body: JSONContent;
  creator_name: string;
  is_pinned: boolean;
  revision: number;
  created_at: string;
  edited_at: string | null;
};
type Page = {
  results: Announcement[];
  count: number;
  next: string | null;
  previous: string | null;
};
type Draft = { item?: Announcement; title: string; body: JSONContent };
type Operation = { path: string; values: Record<string, unknown> };

export function Announcements({
  cohort,
  onBack,
    backLabel = "← 返回班級",
}: {
  cohort?: Cohort;
  onBack?: () => void;
  backLabel?: string;
}) {
  const endpoint = cohort
    ? `/classes/${cohort.id}/announcements/`
    : "/student/announcements/";
  const editable = cohort?.role === "homeroom";
  const [collapsed, setCollapsed] = useState(false);
  const contentId = useId();
  const [data, setData] = useState<Page | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [deleting, setDeleting] = useState<Announcement | null>(null);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const operation = useRef<Operation | null>(null);
  const locked = busy || retry || conflict;
  const load = useCallback(
    async (target: number) => {
      setLoading(true);
      try {
        const result = await api<Page>(`${endpoint}?page=${target}`);
        setData(result);
        setPage(target);
      } finally {
        setLoading(false);
      }
    },
    [endpoint],
  );
  useEffect(() => {
    load(1).catch((e) => setError(e.message));
  }, [load]);
  async function refresh(target = page) {
    setError("");
    try {
      await load(target);
    } catch (e) {
      setError(e instanceof Error ? e.message : "無法讀取公告。");
    }
  }
  async function mutate(path?: string, values?: Record<string, unknown>) {
    if (busy || conflict) return;
    if (!operation.current && path && values)
      operation.current = {
        path,
        values: { ...values, request_id: crypto.randomUUID() },
      };
    const pending = operation.current;
    if (!pending) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(pending.path, "POST", pending.values);
    } catch (e) {
      if (e instanceof ApiError && e.status && e.status < 500) {
        operation.current = null;
        setRetry(false);
        setConflict(e.status === 409 || e.status === 404);
      } else setRetry(true);
      setError(e instanceof Error ? e.message : "連線中斷，請重試這次操作。");
      setBusy(false);
      return;
    }
    operation.current = null;
    setRetry(false);
    setDraft(null);
    setDeleting(null);
    setNotice("公告操作已完成。");
    try {
      await load(1);
    } catch {
      setData(null);
      setError("公告操作已完成，但清單更新失敗，請重新載入公告。");
    } finally {
      setBusy(false);
    }
  }
  return (
      <section className="announcements" aria-label="班級公告">
          {onBack && (
              <button className="text-button" onClick={onBack} disabled={busy}>
                  {backLabel}
              </button>
          )}
        <header className="page-title">
        <div>
          <p className="eyebrow">{cohort?.name || "班級日常"}</p>
          <h1>班級公告</h1>
          {!cohort && data && (
            <p className="muted small">共 {data.count} 則公告</p>
          )}
        </div>
        {!cohort && (
          <button
            className="secondary"
            aria-expanded={!collapsed}
            aria-controls={contentId}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? "全部展開" : "全部收合"}
          </button>
        )}
      </header>
      <div id={contentId} hidden={!cohort && collapsed}>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        {retry && (
          <div className="notice">
            <p>
              尚未確認結果，已保留內容。請重試這次操作；離開此頁前先確認結果。
            </p>
            <button
              className="primary"
              disabled={busy}
              onClick={() => mutate()}
            >
              重試這次操作
            </button>
          </div>
        )}
        {conflict && (
          <button
            className="secondary"
            onClick={() => {
              setDraft(null);
              setDeleting(null);
              setConflict(false);
              void refresh(1);
            }}
          >
            捨棄舊操作並重新載入公告
          </button>
        )}
        <div className="actions">
          {editable && !draft && (
            <button
              className="primary"
              disabled={locked || loading || !!deleting}
              onClick={() => {
                setDraft({ title: "", body: emptyDocument });
                setNotice("");
              }}
            >
              新增公告
            </button>
          )}
          <button
            className="text-button"
            disabled={locked || loading}
            onClick={() => refresh(1)}
          >
            重新載入公告
          </button>
        </div>
        {draft && (
          <form
            className="announcement-form"
            onSubmit={(e) => {
              e.preventDefault();
              void mutate(
                draft.item ? `${endpoint}${draft.item.id}/` : endpoint,
                {
                  title: draft.title,
                  body: draft.body,
                  ...(draft.item
                    ? { action: "edit", revision: draft.item.revision }
                    : {}),
                },
              );
            }}
          >
            <h3>{draft.item ? "編輯公告" : "新增公告"}</h3>
            <label>
              公告標題
              <input
                value={draft.title}
                required
                maxLength={100}
                disabled={locked}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
            </label>
            <Suspense fallback={<p role="status">正在載入編輯器…</p>}>
              <AnnouncementEditor
                key={draft.item?.id || "new"}
                body={draft.body}
                disabled={locked}
                onChange={(body) =>
                  setDraft((old) => (old ? { ...old, body } : old))
                }
              />
            </Suspense>
            <div className="actions">
              <button className="primary" disabled={locked}>
                {draft.item ? "儲存公告" : "發布公告"}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={locked}
                onClick={() => setDraft(null)}
              >
                取消
              </button>
            </div>
          </form>
        )}
        {deleting && (
          <div role="alertdialog" aria-label="刪除公告確認" className="notice">
            <h3>刪除「{deleting.title}」？</h3>
            <p>學生與教師將看不到這則公告，歷史資料仍保留。</p>
            <div className="actions">
              <button
                className="danger"
                disabled={locked}
                onClick={() =>
                  mutate(`${endpoint}${deleting.id}/`, {
                    action: "delete",
                    revision: deleting.revision,
                  })
                }
              >
                確認刪除公告
              </button>
              <button
                className="secondary"
                disabled={locked}
                onClick={() => setDeleting(null)}
              >
                取消
              </button>
            </div>
          </div>
        )}
        {loading && <p role="status">正在載入公告…</p>}
        {data?.results.map((item) => (
          <article className="announcement-card" key={item.id}>
            {item.is_pinned && <span className="badge">置頂</span>}
            <h3>{item.title}</h3>
            <p className="muted small">
              {item.creator_name} ·{" "}
              {new Date(item.created_at).toLocaleString("zh-TW")}
              {item.edited_at && (
                <>
                  {" "}
                  · 已編輯 {new Date(item.edited_at).toLocaleString("zh-TW")}
                </>
              )}
            </p>
            <AnnouncementContent body={item.body} />
            <AnnouncementComments
              endpoint={`${endpoint}${item.id}/comments/`}
              initialCount={item.comment_count}
            />
            {editable && (
              <div className="actions">
                <button
                  className="text-button"
                  disabled={locked || loading || !!draft || !!deleting}
                  onClick={() =>
                    setDraft({ item, title: item.title, body: item.body })
                  }
                >
                  編輯
                </button>
                <button
                  className="text-button"
                  disabled={locked || loading || !!draft || !!deleting}
                  onClick={() =>
                    mutate(`${endpoint}${item.id}/`, {
                      action: "pin",
                      revision: item.revision,
                      is_pinned: !item.is_pinned,
                    })
                  }
                >
                  {item.is_pinned ? "取消置頂" : "置頂"}
                </button>
                <button
                  className="text-button danger-text"
                  disabled={locked || loading || !!draft || !!deleting}
                  onClick={() => setDeleting(item)}
                >
                  刪除
                </button>
              </div>
            )}
          </article>
        ))}
        {data && !data.count && <p className="muted">目前沒有公告。</p>}
        {data && data.count > 10 && (
          <nav className="actions" aria-label="公告分頁">
            <button
              className="secondary"
              disabled={
                !data.previous || locked || loading || !!draft || !!deleting
              }
              onClick={() => refresh(page - 1)}
            >
              上一頁公告
            </button>
            <span>
              第 {page} 頁 · 共 {data.count} 則
            </span>
            <button
              className="secondary"
              disabled={
                !data.next || locked || loading || !!draft || !!deleting
              }
              onClick={() => refresh(page + 1)}
            >
              下一頁公告
            </button>
          </nav>
        )}
      </div>
    </section>
  );
}
