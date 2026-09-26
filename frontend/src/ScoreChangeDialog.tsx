import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "./api";
import type { ScoreRecord } from "./ScoreHistory";

type Preview = {
  token: string;
  targets: ScoreRecord[];
  skipped: (ScoreRecord & { skip_reason: string })[];
};
export type ScoreManagement = {
  base: string;
  teacherId: number;
  homeroom: boolean;
  templates: Record<"positive" | "negative", Record<string, string>>;
  onSaved: () => void;
};

export function ScoreChangeDialog({
  record,
  mode,
  management,
  onClose,
}: {
  record: ScoreRecord;
  mode: "single" | "batch" | "delete";
  management: ScoreManagement;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [kind, setKind] = useState(record.kind);
  const [score, setScore] = useState(String(record.score));
  const [template, setTemplate] = useState(record.template);
  const [note, setNote] = useState(record.note);
  const requests = useRef(new Map<string, string>());
  const submitting = useRef(false);
  const deleting = mode === "delete";
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setPreview(null);
    api<Preview>(
      `${management.base}scores/${record.id}/edit-preview/?scope=${mode === "batch" ? "batch" : "single"}`,
    )
      .then((result) => {
        if (!active) return;
        setPreview(result);
        const initial = result.targets[0];
        if (initial) {
          setKind(initial.kind);
          setScore(String(initial.score));
          setTemplate(initial.template);
          setNote(initial.note);
        }
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
  }, [management.base, record.id, mode, reload]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!preview || submitting.current) return;
    const payload = {
      action: deleting ? "delete" : "edit",
      preview_token: preview.token,
      ...(!deleting
        ? { kind, score: Number(score), template, note: note.trim() }
        : {}),
    };
    const key = JSON.stringify(payload);
    const requestId = requests.current.get(key) || crypto.randomUUID();
    requests.current.set(key, requestId);
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`${management.base}score-changes/`, "POST", {
        ...payload,
        request_id: requestId,
      });
      management.onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "儲存失敗，請重試。");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="student-dialog"
      aria-labelledby="score-change-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <form onSubmit={submit}>
        <h2 id="score-change-title">
          {deleting
            ? "刪除分數紀錄"
            : mode === "batch"
              ? "修改同批紀錄"
              : "修改這筆紀錄"}
        </h2>
        <p className="muted">
          {deleting
            ? "刪除後不再計入總分，學生不再看見此筆；導師仍可查核歷史。已發放點數不回收。"
            : "儲存後同步更新總分，保留原建立教師與修改歷史。"}
        </p>
        {mode === "batch" && (
          <p className="notice">
            以下分數及原因套用到本次名單。已個別修改（含補原因）及已刪除者略過；名單內任一筆在預覽後更動，整批取消。
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {loading ? (
          <p role="status">正在載入預覽…</p>
        ) : (
          preview && (
            <>
              <h3>
                本次{deleting ? "刪除" : "修改"} {preview.targets.length} 筆
              </h3>
              <ul className="score-preview-list">
                {preview.targets.map((r) => (
                  <li key={r.id}>
                    {r.seat_number} 號 · {r.student_name}：{r.score} 分 ·{" "}
                    {r.reason}
                    {r.note ? ` · ${r.note}` : ""}
                  </li>
                ))}
              </ul>
              {preview.skipped.length > 0 && (
                <details open>
                  <summary>略過 {preview.skipped.length} 筆</summary>
                  <ul className="score-preview-list">
                    {preview.skipped.map((r) => (
                      <li key={r.id}>
                        {r.seat_number} 號 · {r.student_name}：{r.skip_reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {!deleting && preview.targets.length > 0 && (
                <fieldset disabled={busy}>
                  <div className="form-row">
                    <label>
                      加扣分種類
                      <select
                        value={kind}
                        onChange={(e) => {
                          const next = e.target.value as typeof kind;
                          setKind(next);
                          setScore(next === "positive" ? "1" : "-1");
                          setTemplate("other");
                        }}
                      >
                        <option value="positive">加分</option>
                        <option value="negative">扣分</option>
                      </select>
                    </label>
                    <label>
                      分數
                      <input
                        type="number"
                        required
                        step={1}
                        min={kind === "positive" ? 0 : -100}
                        max={kind === "positive" ? 100 : 0}
                        value={score}
                        onChange={(e) => setScore(e.target.value)}
                      />
                    </label>
                  </div>
                  <label>
                    原因模板
                    <select
                      value={template}
                      onChange={(e) => setTemplate(e.target.value)}
                    >
                      {Object.entries(management.templates[kind]).map(
                        ([key, value]) => (
                          <option key={key} value={key}>
                            {value}
                          </option>
                        ),
                      )}
                      <option value="other">其他</option>
                    </select>
                  </label>
                  <label>
                    補充原因（選填）
                    <textarea
                      rows={3}
                      maxLength={1000}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </label>
                  {template === "other" && !note.trim() && (
                    <p className="muted small">留白會標記為待補原因。</p>
                  )}
                </fieldset>
              )}
            </>
          )
        )}
        <div className="actions">
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="text-button"
            disabled={busy || loading}
            onClick={() => setReload((v) => v + 1)}
          >
            重新載入預覽
          </button>
          <button
            className={deleting ? "danger-button" : "primary"}
            disabled={busy || loading || !preview?.targets.length}
          >
            {busy ? "儲存中…" : deleting ? "確認刪除紀錄" : "確認儲存修改"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
