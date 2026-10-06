import { createRequestId } from "./requestId";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError, type Cohort } from "./api";
import type { ScoreRecord } from "./ScoreHistory";

type AwardPage = {
  students: {
    id: number;
    name: string;
    seat_number: number;
    point_balance: number;
    records: ScoreRecord[];
  }[];
  count: number;
  next: string | null;
  previous: string | null;
  week: { start: string; end: string; points: number; count: number };
};

export function PointAwards({
  cohort,
  onBack,
  backLabel = "← 返回我的班級",
}: {
  cohort: Cohort;
  onBack: () => void;
  backLabel?: string;
}) {
  const [data, setData] = useState<AwardPage | null>(null);
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<number[]>([]);
  const [points, setPoints] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requests = useRef(new Map<string, string>());
  const submitting = useRef(false);
  const base = `/classes/${cohort.id}/point-awards/`;
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setSelected([]);
    setPoints({});
    api<AwardPage>(`${base}?status=${status}&page=${page}`)
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
  }, [base, status, page, revision]);
  const records = data?.students.flatMap((s) => s.records) ?? [];
  const chosen = records.filter((r) => selected.includes(r.id));
  const amount = (id: number) => points[id] ?? "1";
  const invalid = chosen.some(
    (r) =>
      !/^\d+$/.test(amount(r.id)) ||
      Number(amount(r.id)) < 1 ||
      Number(amount(r.id)) > 100,
  );
  const total = chosen.reduce((sum, r) => sum + Number(amount(r.id)), 0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || !chosen.length || invalid || chosen.length > 200)
      return;
    const items = chosen
      .map((r) => ({
        record_id: r.id,
        revision: r.revision,
        points: Number(amount(r.id)),
      }))
      .sort((a, b) => a.record_id - b.record_id);
    const key = JSON.stringify(items);
    const requestId = requests.current.get(key) ?? createRequestId();
    requests.current.set(key, requestId);
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await api<{ results: { points: number }[] }>(base, "POST", {
        items,
        request_id: requestId,
      });
      requests.current.delete(key);
      setNotice(
        `已發放 ${saved.results.reduce((sum, r) => sum + r.points, 0)} 點，共 ${saved.results.length} 筆。`,
      );
      setSelected([]);
      setPoints({});
      setPage(1);
      setRevision((v) => v + 1);
    } catch (e) {
      const unavailable =
        e instanceof ApiError
          ? e.unavailableIds
              .map((id) => {
                const record = records.find((r) => r.id === id);
                return record
                  ? `${record.seat_number} 號 ${record.student_name}（${record.reason}）`
                  : "已失效紀錄";
              })
              .join("、")
          : "";
      setError(
        (e instanceof Error ? e.message : "發點失敗，請重試。") +
          (unavailable ? `（${unavailable}）` : ""),
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <button className="text-button" disabled={busy} onClick={onBack}>
        {backLabel}
      </button>
      <header>
        <p className="eyebrow">{cohort.name} / 教學獎勵</p>
        <h1>發點數</h1>
        <p className="muted">
          選取自己建立的加分紀錄，事後決定獎勵。每筆來源只能發放一次。
        </p>
      </header>
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
      <div className="actions award-toolbar">
        <label>
          發點狀態
          <select
            value={status}
            disabled={busy || loading}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
              setNotice("");
            }}
          >
            <option value="pending">尚未發點</option>
            <option value="awarded">已發點紀錄</option>
          </select>
        </label>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={() => {
            setRevision((v) => v + 1);
            setNotice("");
          }}
        >
          重新整理發點名單
        </button>
      </div>
      {loading ? (
        <p role="status">正在載入發點名單…</p>
      ) : (
        data && (
          <>
            <p className="score-total">
              本週本人已發放 {data.week.points} 點 · {data.week.count} 筆
            </p>
            <p className="muted small">
              本班統計 · 台北時間週一至週日 · 無每週額度限制
            </p>
            {data.students.length === 0 ? (
              <p className="notice">
                {status === "pending"
                  ? "目前沒有可發點的紀錄。"
                  : "目前沒有已發點紀錄。"}
              </p>
            ) : (
              <form className="award-form" onSubmit={submit}>
                <fieldset disabled={busy}>
                  {status === "pending" && (
                    <>
                      <p className="muted">
                        每筆預設 1 點，可填 1～100 整數；一次最多選 200
                        筆。任何一筆失效，整批都不發放。
                      </p>
                      <div className="actions">
                        <button
                          type="button"
                          className="secondary"
                          disabled={records.length > 200}
                          onClick={() => setSelected(records.map((r) => r.id))}
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
                    </>
                  )}
                  {data.students.map((student) => (
                    <section
                      className="editor"
                      key={student.id}
                      aria-label={`${student.seat_number} 號 · ${student.name}`}
                    >
                      <h2>
                        {student.seat_number} 號 · {student.name}
                      </h2>
                      <ul className="score-list">
                        {student.records.map((record) => (
                          <li className="score-record" key={record.id}>
                            <div className="score-record-top">
                              <strong>
                                {record.kind === "positive" ? "加分" : "扣分"}{" "}
                                {record.score}
                              </strong>
                              {record.awarded_points !== null && (
                                <span className="badge">
                                  已發放 {record.awarded_points} 點
                                </span>
                              )}
                              {record.deleted_at && (
                                <span className="badge">來源已刪除</span>
                              )}
                            </div>
                            <p>
                              {record.reason}
                              {record.is_modified && (
                                <span className="badge">已修改</span>
                              )}
                            </p>
                            {record.note && <p>{record.note}</p>}
                            <p className="muted small">
                              {new Date(record.created_at).toLocaleString(
                                "zh-TW",
                              )}
                            </p>
                            {status === "pending" && (
                              <div className="form-row">
                                <label className="check-row">
                                  <input
                                    type="checkbox"
                                    checked={selected.includes(record.id)}
                                    disabled={
                                      !selected.includes(record.id) &&
                                      selected.length >= 200
                                    }
                                    onChange={(e) =>
                                      setSelected((ids) =>
                                        e.target.checked
                                          ? [...ids, record.id]
                                          : ids.filter(
                                              (id) => id !== record.id,
                                            ),
                                      )
                                    }
                                  />
                                  選取此筆
                                </label>
                                <label>
                                  發放點數
                                  <input
                                    aria-label={`${student.name}的發放點數`}
                                    type="number"
                                    min={1}
                                    max={100}
                                    step={1}
                                    required
                                    disabled={!selected.includes(record.id)}
                                    value={amount(record.id)}
                                    onChange={(e) =>
                                      setPoints((values) => ({
                                        ...values,
                                        [record.id]: e.target.value,
                                      }))
                                    }
                                  />
                                </label>
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))}
                  {status === "pending" && (
                    <>
                      <p>
                        已選 {chosen.length} 筆 · 合計 {invalid ? "—" : total}{" "}
                        點
                      </p>
                      <button
                        className="primary"
                        disabled={
                          busy ||
                          !chosen.length ||
                          invalid ||
                          chosen.length > 200
                        }
                      >
                        {busy ? "發放中…" : "發放所選點數"}
                      </button>
                    </>
                  )}
                </fieldset>
              </form>
            )}
            <div className="actions">
              <button
                className="secondary"
                disabled={busy || !data.previous}
                onClick={() => setPage((p) => p - 1)}
              >
                上一頁
              </button>
              <span>
                第 {page} 頁 · 共 {data.count} 位學生
              </span>
              <button
                className="secondary"
                disabled={busy || !data.next}
                onClick={() => setPage((p) => p + 1)}
              >
                下一頁
              </button>
            </div>
          </>
        )
      )}
    </>
  );
}
