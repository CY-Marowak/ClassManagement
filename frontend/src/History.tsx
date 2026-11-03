import { useEffect, useRef, useState } from "react";
import { api, type Cohort, type Student } from "./api";

type Filters = { start: string; end: string; kind: string; student_id: string };
type HistoryPage = {
  count: number;
  next: string | null;
  previous: string | null;
  columns: { key: string; label: string }[];
  results: Record<string, string | number>[];
};
const empty: Filters = { start: "", end: "", kind: "", student_id: "" };

export function History({
  cohort,
  onBack,
}: {
  cohort?: Cohort;
  onBack: () => void;
}) {
  const [kind, setKind] = useState<"scores" | "points">("scores");
  const [draft, setDraft] = useState<Filters>(empty);
  const [query, setQuery] = useState({ filters: empty, page: 1, revision: 0 });
  const [result, setResult] = useState<{
    key: string;
    data: HistoryPage;
  } | null>(null);
  const [error, setError] = useState("");
  const [roster, setRoster] = useState<Student[]>([]);
  const [rosterError, setRosterError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const download = useRef<AbortController | null>(null);
  const base = cohort
    ? `/classes/${cohort.id}/history/${kind}/`
    : `/student/history/${kind}/`;
  const params = new URLSearchParams(
    Object.entries(query.filters).filter(([, value]) => value !== ""),
  );
  const filterString = params.toString();
  params.set("page", String(query.page));
  const endpoint = `${base}?${params}`;
  const key = `${endpoint}:${query.revision}`;
  const data = result?.key === key ? result.data : null;
  const unapplied = JSON.stringify(draft) !== JSON.stringify(query.filters);
  useEffect(() => () => download.current?.abort(), []);
  useEffect(() => {
    let active = true;
    setError("");
    api<HistoryPage>(endpoint)
      .then((data) => {
        if (active) setResult({ key, data });
      })
      .catch((e) => {
        if (active) {
          setResult(null);
          setError(e.message);
        }
      });
    return () => {
      active = false;
    };
  }, [endpoint, key]);
  useEffect(() => {
    let active = true;
    setRoster([]);
    setRosterError("");
    if (cohort)
      api<Student[]>(`/classes/${cohort.id}/students/`)
        .then((rows) => {
          if (active) setRoster(rows);
        })
        .catch((e) => {
          if (active) setRosterError(e.message);
        });
    return () => {
      active = false;
    };
  }, [cohort?.id]);
  function selectKind(next: "scores" | "points") {
    setKind(next);
    setDraft(empty);
    setQuery({ filters: empty, page: 1, revision: query.revision + 1 });
  }
  async function exportCsv() {
    setDownloading(true);
    setError("");
    const controller = new AbortController();
    download.current = controller;
    try {
      const response = await fetch(`/api${base}export/?${filterString}`, {
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        throw new Error(failure.detail || "無法下載，請重新載入明細後再試。");
      }
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cm-${kind}.csv`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      if (!controller.signal.aborted) {
        setResult(null);
        setError(e instanceof Error ? e.message : "無法下載。");
      }
    } finally {
      if (!controller.signal.aborted) setDownloading(false);
    }
  }
  return (
    <section aria-label="完整明細與匯出" className="history-page">
      <button className="text-button" disabled={downloading} onClick={onBack}>
        {cohort ? "← 返回工作首頁" : "← 返回我的頁面"}
      </button>
      <h1>{cohort ? `${cohort.name} · 明細與匯出` : "我的完整明細"}</h1>
      <p className="muted">
        分數與點數分開查看；日期依台北時間，包含起日與迄日。
      </p>
      <div className="actions" aria-label="明細種類">
        <button
          className={kind === "scores" ? "primary" : "secondary"}
          aria-pressed={kind === "scores"}
          disabled={downloading}
          onClick={() => selectKind("scores")}
        >
          分數明細
        </button>
        <button
          className={kind === "points" ? "primary" : "secondary"}
          aria-pressed={kind === "points"}
          disabled={downloading}
          onClick={() => selectKind("points")}
        >
          點數明細
        </button>
      </div>
      <form
        className="history-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery({
            filters: { ...draft },
            page: 1,
            revision: query.revision + 1,
          });
        }}
      >
        <label>
          起日
          <input
            type="date"
            value={draft.start}
            disabled={downloading}
            onChange={(e) => setDraft({ ...draft, start: e.target.value })}
          />
        </label>
        <label>
          迄日
          <input
            type="date"
            value={draft.end}
            disabled={downloading}
            onChange={(e) => setDraft({ ...draft, end: e.target.value })}
          />
        </label>
        {kind === "points" && (
          <label>
            交易類型
            <select
              value={draft.kind}
              disabled={downloading}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
            >
              <option value="">全部類型</option>
              <option value="award">獲得點數</option>
              <option value="feed">餵食</option>
              <option value="purchase">購買角色</option>
            </select>
          </label>
        )}
        {cohort && (
          <label>
            學生
            <select
              value={draft.student_id}
              disabled={downloading || !!rosterError}
              onChange={(e) =>
                setDraft({ ...draft, student_id: e.target.value })
              }
            >
              <option value="">全班學生</option>
              {roster.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.seat_number} 號 · {s.name}（{s.student_number}）
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="actions">
          <button className="primary" disabled={downloading}>
            套用篩選
          </button>
          <button
            className="secondary"
            type="button"
            disabled={downloading}
            onClick={() => {
              setDraft(empty);
              setQuery({
                filters: empty,
                page: 1,
                revision: query.revision + 1,
              });
            }}
          >
            清除篩選
          </button>
        </div>
      </form>
      {rosterError && (
        <p role="alert" className="error">
          學生名單載入失敗：{rosterError}。請返回後重新開啟。
        </p>
      )}
      {unapplied && (
        <p role="status">條件已修改，請按「套用篩選」更新明細與下載範圍。</p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">正在載入明細…</p>}
      <button
        className="secondary"
        disabled={!data || unapplied || downloading}
        onClick={exportCsv}
      >
        {downloading ? "正在準備 CSV…" : "下載目前篩選的 CSV"}
      </button>
      <p className="muted small">
        下載全部符合條件的紀錄，不限目前頁面。
        {cohort && "學號欄請以文字格式匯入試算表，以保留前導零。"}
      </p>
      {data && (
        <>
          <p role="status">
            共 {data.count} 筆 · 第 {query.page} 頁 · 由新到舊
          </p>
          {data.results.length === 0 && (
            <p>沒有符合條件的紀錄；仍可下載欄位表頭。</p>
          )}
          <ol className="history-records">
            {data.results.map((row) => (
              <li key={row.id} className="history-record">
                <dl>
                  {data.columns.map((column) => (
                    <div key={column.key}>
                      <dt>{column.label}</dt>
                      <dd>{row[column.key] === "" ? "—" : row[column.key]}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ol>
          <div className="actions">
            <button
              className="secondary"
              disabled={!data.previous || downloading || unapplied}
              onClick={() => setQuery({ ...query, page: query.page - 1 })}
            >
              上一頁
            </button>
            <button
              className="secondary"
              disabled={!data.next || downloading || unapplied}
              onClick={() => setQuery({ ...query, page: query.page + 1 })}
            >
              下一頁
            </button>
          </div>
        </>
      )}
    </section>
  );
}
