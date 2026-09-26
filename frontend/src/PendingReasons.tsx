import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import { type ScorePage, type ScoreRecord } from "./ScoreHistory";

export function PendingReasons({
  base,
  active,
  onBusy,
}: {
  base: string;
  active: boolean;
  onBusy: (busy: boolean) => void;
}) {
  const [data, setData] = useState<ScorePage | null>(null);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<ScoreRecord[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requests = useRef(new Map<string, string>());
  const submitting = useRef(false);

  useEffect(() => {
    if (!active) return;
    let current = true;
    setLoading(true);
    setError("");
    api<ScorePage>(`${base}pending-reasons/?page=${page}`)
      .then((result) => {
        if (current) setData(result);
      })
      .catch((e) => {
        if (current) {
          setError(e.message);
          setData(null);
        }
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [base, active, page, revision]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || !selected.length || !note.trim()) return;
    const payload = {
      record_ids: selected.map((r) => r.id).sort((a, b) => a - b),
      note: note.trim(),
    };
    const fingerprint = JSON.stringify(payload);
    const requestId = requests.current.get(fingerprint) || crypto.randomUUID();
    requests.current.set(fingerprint, requestId);
    submitting.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await api<{ results: ScoreRecord[] }>(
        base + "pending-reasons/",
        "POST",
        { ...payload, request_id: requestId },
      );
      requests.current.delete(fingerprint);
      setNotice(`已補齊 ${saved.results.length} 筆原因，分數不變。`);
      setSelected([]);
      setNote("");
      setPage(1);
      setRevision((x) => x + 1);
    } catch (e) {
      const unavailable =
        e instanceof ApiError
          ? e.unavailableIds
              .map((id) => {
                const record = selected.find((r) => r.id === id);
                return record
                  ? `${record.seat_number} 號 ${record.student_name}`
                  : "已失效紀錄";
              })
              .join("、")
          : "";
      setError(
        (e instanceof Error ? e.message : "儲存失敗，請重試。") +
          (unavailable ? `（${unavailable}）` : ""),
      );
    } finally {
      submitting.current = false;
      setBusy(false);
      onBusy(false);
    }
  }

  if (!active) return null;
  return (
    <section className="pending-reasons" aria-label="待補原因整理">
      <p className="muted">
        這裡只列出你有權補齊的紀錄。導師可補全班，共同教師可補自己的紀錄。
      </p>
      <button
        className="text-button"
        disabled={busy || loading}
        onClick={() => {
          setSelected([]);
          setNotice("");
          setPage(1);
          setRevision((x) => x + 1);
        }}
      >
        重新整理待補原因
      </button>
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
      {loading ? (
        <p>正在載入待補紀錄…</p>
      ) : (
        data && (
          <form onSubmit={submit}>
            <fieldset disabled={busy}>
              <p>
                可補原因共 {data.count} 筆 · 已選 {selected.length} 筆
              </p>
              {data.results.length ? (
                <>
                  <div className="actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setSelected(data.results)}
                    >
                      全選本頁
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setSelected([])}
                    >
                      清除選取
                    </button>
                  </div>
                  <div className="pending-list">
                    {data.results.map((record) => (
                      <label
                        className="check-row pending-record"
                        key={record.id}
                      >
                        <input
                          type="checkbox"
                          checked={selected.some((r) => r.id === record.id)}
                          onChange={(e) =>
                            setSelected((old) =>
                              e.target.checked
                                ? [...old, record]
                                : old.filter((r) => r.id !== record.id),
                            )
                          }
                        />
                        <span>
                          <strong>
                            {record.seat_number} 號 · {record.student_name} ·{" "}
                            {record.kind === "positive" ? "加分" : "扣分"}{" "}
                            {record.score}
                          </strong>
                          <br />
                          <span className="muted small">
                            {record.creator_name} ·{" "}
                            {new Date(record.created_at).toLocaleString(
                              "zh-TW",
                            )}
                            {record.batch_id &&
                              ` · 同批記分 ${record.batch_id.slice(0, 8)}`}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </>
              ) : (
                <p>目前沒有可補的原因。</p>
              )}
              {selected.some(
                (r) => !data.results.some((item) => item.id === r.id),
              ) && (
                <p className="notice">
                  部分已選紀錄已不在此頁；若上次回應遺失可用相同內容重試，否則請清除選取或重新整理。
                </p>
              )}
              {(data.results.length > 0 || selected.length > 0) && (
                <>
                  <label>
                    統一補充原因
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={1000}
                      required
                      rows={3}
                    />
                  </label>
                  <p className="muted small">
                    套用至已選紀錄。若其中一筆已補完或失效，整批都不儲存。
                  </p>
                  <button
                    className="primary"
                    disabled={!selected.length || !note.trim()}
                  >
                    儲存原因
                  </button>
                </>
              )}
              <nav className="actions" aria-label="待補原因分頁">
                <button
                  type="button"
                  className="secondary"
                  disabled={!data.previous}
                  onClick={() => {
                    setSelected([]);
                    setPage((x) => x - 1);
                  }}
                >
                  上一頁
                </button>
                <span>第 {page} 頁</span>
                <button
                  type="button"
                  className="secondary"
                  disabled={!data.next}
                  onClick={() => {
                    setSelected([]);
                    setPage((x) => x + 1);
                  }}
                >
                  下一頁
                </button>
              </nav>
            </fieldset>
          </form>
        )
      )}
    </section>
  );
}
