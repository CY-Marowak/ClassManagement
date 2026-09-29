import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { JSONContent } from "@tiptap/react";
import { api, ApiError } from "./api";
import { AnnouncementContent, emptyDocument } from "./AnnouncementContent";

const Editor = lazy(() =>
  import("./AnnouncementEditor").then((module) => ({
    default: module.AnnouncementEditor,
  })),
);
type Comment = {
  id: number;
  body: JSONContent;
  creator_name: string;
  created_at: string;
  edited_at: string | null;
  revision: number;
  can_edit: boolean;
  can_delete: boolean;
};
type CommentPage = {
  count: number;
  next: string | null;
  previous: string | null;
  can_create: boolean;
  results: Comment[];
};
type Pending = {
  path: string;
  values: Record<string, unknown>;
  creating: boolean;
};

export function AnnouncementComments({
  endpoint,
  initialCount,
}: {
  endpoint: string;
  initialCount: number;
}) {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(initialCount);
  const [data, setData] = useState<CommentPage | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Comment | null>(null);
  const [deleting, setDeleting] = useState<Comment | null>(null);
  const [body, setBody] = useState<JSONContent>(emptyDocument);
  const [editorVersion, setEditorVersion] = useState(0);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const pending = useRef<Pending | null>(null);
  const locked = busy || retry || conflict;
  useEffect(() => {
    setCount(initialCount);
  }, [initialCount]);

  async function load(target: number): Promise<CommentPage> {
    const result = await api<CommentPage>(`${endpoint}?page=${target}`);
    setData(result);
    setPage(target);
    setCount(result.count);
    return result;
  }
  async function refresh(target = page) {
    setLoading(true);
    setError("");
    try {
      try {
        await load(target);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404 && target > 1)
          await load(1);
        else throw e;
      }
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "無法讀取留言。");
    } finally {
      setLoading(false);
    }
  }
  function clearDraft() {
    setEditing(null);
    setDeleting(null);
    setBody(emptyDocument);
    setEditorVersion((v) => v + 1);
  }
  async function mutate(
    operation?: Omit<Pending, "values"> & { values: Record<string, unknown> },
  ) {
    if (busy || conflict) return;
    if (!pending.current && operation)
      pending.current = {
        ...operation,
        values: { ...operation.values, request_id: crypto.randomUUID() },
      };
    const request = pending.current;
    if (!request) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(request.path, "POST", request.values);
    } catch (e) {
      if (e instanceof ApiError && e.status && e.status < 500) {
        pending.current = null;
        setRetry(false);
        setConflict([403, 404, 409].includes(e.status));
      } else setRetry(true);
      setError(
        e instanceof Error ? e.message : "連線中斷，請重試這次留言操作。",
      );
      setBusy(false);
      return;
    }
    pending.current = null;
    setRetry(false);
    clearDraft();
    setNotice("留言操作已完成。");
    try {
      const first = await load(1);
      const target = request.creating
        ? Math.max(1, Math.ceil(first.count / 20))
        : Math.min(page, Math.max(1, Math.ceil(first.count / 20)));
      if (target > 1) await load(target);
    } catch {
      setData(null);
      setError("留言操作已完成，但清單更新失敗，請更新留言確認結果。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="announcement-comments" aria-label="公告留言">
      <button
        className="text-button"
        aria-expanded={open}
        disabled={busy || loading}
        onClick={() => {
          setOpen(!open);
          if (!open && !locked) void refresh(1);
        }}
      >
        留言（{count}）
      </button>
      {open && (
        <div>
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
          {retry && (
            <div className="notice">
              <p>內容已保留，請重試確認原操作；離開公告頁前先確認結果。</p>
              <button
                className="primary"
                disabled={busy}
                onClick={() => mutate()}
              >
                重試這次留言操作
              </button>
            </div>
          )}
          {conflict && (
            <button
              className="secondary"
              onClick={() => {
                clearDraft();
                setConflict(false);
                void refresh(1);
              }}
            >
              捨棄舊操作並重新載入留言
            </button>
          )}
          <button
            className="text-button"
            disabled={locked || loading}
            onClick={() => refresh()}
          >
            更新留言
          </button>
          {loading && <p role="status">正在載入留言…</p>}
          {data?.results.map((item) => (
            <article key={item.id} className="comment-card">
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
              <div className="actions">
                {item.can_edit && (
                  <button
                    className="text-button"
                    disabled={locked || loading || !!editing || !!deleting}
                    onClick={() => {
                      setEditing(item);
                      setBody(item.body);
                      setEditorVersion((v) => v + 1);
                      setNotice("");
                    }}
                  >
                    編輯留言
                  </button>
                )}
                {item.can_delete && (
                  <button
                    className="text-button danger-text"
                    disabled={locked || loading || !!editing || !!deleting}
                    onClick={() => setDeleting(item)}
                  >
                    刪除留言
                  </button>
                )}
              </div>
            </article>
          ))}
          {data && !data.count && <p className="muted">目前沒有留言。</p>}
          {deleting && (
            <div
              role="alertdialog"
              aria-label="刪除留言確認"
              className="notice"
            >
              <p>
                確定刪除 {deleting.creator_name}{" "}
                的這則留言？刪除後班級成員將看不到，歷史資料仍保留。
              </p>
              <AnnouncementContent body={deleting.body} />
              <div className="actions">
                <button
                  className="danger-button"
                  disabled={locked}
                  onClick={() =>
                    mutate({
                      path: `${endpoint}${deleting.id}/`,
                      values: { action: "delete", revision: deleting.revision },
                      creating: false,
                    })
                  }
                >
                  確認刪除留言
                </button>
                <button
                  className="secondary"
                  disabled={locked}
                  onClick={() => setDeleting(null)}
                >
                  取消刪除留言
                </button>
              </div>
            </div>
          )}
          {data && data.count > 20 && (
            <nav className="actions" aria-label="留言分頁">
              <button
                className="secondary"
                disabled={
                  !data.previous || locked || loading || !!editing || !!deleting
                }
                onClick={() => refresh(page - 1)}
              >
                上一頁留言
              </button>
              <span>
                第 {page} 頁 · 共 {data.count} 則
              </span>
              <button
                className="secondary"
                disabled={
                  !data.next || locked || loading || !!editing || !!deleting
                }
                onClick={() => refresh(page + 1)}
              >
                下一頁留言
              </button>
            </nav>
          )}
          {(data?.can_create || editing) && !deleting && (
            <form
              className="comment-form"
              onSubmit={(e) => {
                e.preventDefault();
                void mutate({
                  path: editing ? `${endpoint}${editing.id}/` : endpoint,
                  values: {
                    body,
                    ...(editing
                      ? { action: "edit", revision: editing.revision }
                      : {}),
                  },
                  creating: !editing,
                });
              }}
            >
              <h4>{editing ? "編輯留言" : "新增留言"}</h4>
              <Suspense fallback={<p role="status">正在載入編輯器…</p>}>
                <Editor
                  key={editorVersion}
                  label="留言內文"
                  maxLength={1000}
                  body={body}
                  disabled={locked || loading}
                  onChange={setBody}
                />
              </Suspense>
              <div className="actions">
                <button className="primary" disabled={locked || loading}>
                  {editing ? "儲存留言" : "發布留言"}
                </button>
                {editing && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={locked || loading}
                    onClick={clearDraft}
                  >
                    取消編輯留言
                  </button>
                )}
              </div>
            </form>
          )}
        </div>
      )}
    </section>
  );
}
