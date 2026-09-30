import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { api, ApiError, type Student } from "./api";
import { AnimalAvatar, animalNames } from "./AnimalAvatar";

type MascotState = {
  animal: Student["avatar"];
  exp: number;
  level: number;
  level_start_exp: number;
  next_level_exp: number;
  remaining_exp: number;
};
type PointEntry = {
  id: number;
  kind: "award" | "feed";
  points: number;
  created_at: string;
  source: {
    id: number;
    reason: string;
    note: string;
    is_modified: boolean;
    is_deleted: boolean;
  } | null;
};
type StudentMascotState = {
  mascot: MascotState;
  point_balance: number;
  daily_remaining: number;
  daily_reset_at: string;
  transactions: PointEntry[];
};
type FeedRequest = { request_id: string; points: number };

export function Mascot({
  cohortId,
  studentId,
  onBack,
  backLabel = "← 返回班級",
  onBalance,
}: {
  cohortId: number;
  studentId?: number;
  onBack: () => void;
  backLabel?: string;
  onBalance?: (balance: number) => void;
}) {
  const [mascot, setMascot] = useState<MascotState | null>(null);
  const [account, setAccount] = useState<StudentMascotState | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [points, setPoints] = useState(1);
  const readVersion = useRef(0);
  const storageKey = `cm-feed-${studentId}`;
  const [pending, setPending] = useState<FeedRequest | null>(() => {
    if (!studentId) return null;
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      return value &&
        typeof value.request_id === "string" &&
        Number.isInteger(value.points) &&
        value.points >= 1 &&
        value.points <= 5
        ? value
        : null;
    } catch {
      return null;
    }
  });
  const reload = useCallback(async () => {
    const version = ++readVersion.current;
    try {
      if (studentId) {
        const result = await api<StudentMascotState>("/student/mascot/");
        if (version !== readVersion.current) return;
        setAccount(result);
        setMascot(result.mascot);
      } else {
        const result = await api<MascotState>(`/classes/${cohortId}/mascot/`);
        if (version === readVersion.current) setMascot(result);
      }
    } catch (e) {
      if (version === readVersion.current) throw e;
    }
  }, [cohortId, studentId]);
  async function refresh() {
    setLoading(true);
    setError("");
    try {
      await reload();
    } catch (e) {
      setAccount(null);
      setMascot(null);
      setError(e instanceof Error ? e.message : "無法更新吉祥物。");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    reload()
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      readVersion.current++;
    };
  }, [reload]);
  useEffect(() => {
    if (account) onBalance?.(account.point_balance);
  }, [account, onBalance]);
  useEffect(() => {
    if (!account) return;
    const timer = window.setTimeout(
      () => {
        reload().catch(() => setError("今日額度更新失敗，請按重新整理。"));
      },
      Math.max(1000, Date.parse(account.daily_reset_at) - Date.now() + 100),
    );
    return () => clearTimeout(timer);
  }, [account, reload]);

  async function feed(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    readVersion.current++;
    const request = pending || { points, request_id: crypto.randomUUID() };
    setError("");
    setNotice("");
    setBusy(true);
    try {
      // Keep an unresolved operation across reloads so lost responses never create a new debit.
      sessionStorage.setItem(storageKey, JSON.stringify(request));
      setPending(request);
      await api<PointEntry>("/student/mascot/", "POST", request);
      sessionStorage.removeItem(storageKey);
      setPending(null);
      setPoints(1);
      setNotice(`餵食成功，班級吉祥物增加 ${request.points} exp。`);
      try {
        await reload();
      } catch {
        setAccount(null);
        setError("餵食已完成，但畫面更新失敗，請重新整理。");
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        sessionStorage.removeItem(storageKey);
        setPending(null);
        await reload().catch(() => setAccount(null));
      }
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        setAccount(null);
        setMascot(null);
      }
      setError(
        e instanceof Error ? e.message : "未能確認餵食結果，請重試這次餵食。",
      );
    } finally {
      setBusy(false);
    }
  }
  const max = account
    ? Math.min(5, account.daily_remaining, account.point_balance)
    : 0;
  return (
    <section className="mascot-page" aria-label="班級吉祥物">
      <div className="page-title">
        <button className="text-button" disabled={busy} onClick={onBack}>
          {studentId ? "返回我的頁面" : backLabel}
        </button>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={refresh}
        >
          重新整理吉祥物
        </button>
      </div>
      <h1>班級吉祥物</h1>
      <p className="muted">一起累積成長，每一份心意都由你決定。</p>
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
      {loading && <p role="status">正在載入吉祥物…</p>}
      {mascot && (
        <div className="mascot-growth">
          <div
            className="mascot-art"
            role="img"
            aria-label={`班級${animalNames[mascot.animal]}吉祥物`}
          >
            <div aria-hidden="true">
              <AnimalAvatar animal={mascot.animal} />
            </div>
            <span aria-hidden="true">✦</span>
          </div>
          <p className="eyebrow">全班共同養成</p>
          <h2>
            {animalNames[mascot.animal]}夥伴 · Lv.{mascot.level}
          </h2>
          <p>累積總餵食量 {mascot.exp} exp</p>
          <progress
            aria-label="本級成長進度"
            value={mascot.exp - mascot.level_start_exp}
            max={mascot.next_level_exp - mascot.level_start_exp}
          />
          <p>距下一級還需 {mascot.remaining_exp} exp</p>
        </div>
      )}
      {studentId && account && (
        <>
          <div className="feeding-summary">
            <p>
              可用點數 <strong>{account.point_balance}</strong>
            </p>
            <p>
              今日還可餵 <strong>{account.daily_remaining}</strong> 點
            </p>
          </div>
          <form className="feeding-form" onSubmit={feed}>
            <p className="muted">
              1 點換 1 exp。每日最多 5 點，台北時間 00:00 重置。
            </p>
            {pending && (
              <p role="status">
                有一筆 {pending.points} 點餵食等待確認；重試不會重複扣點。
              </p>
            )}
            <label>
              餵食點數
              <select
                value={pending?.points ?? points}
                disabled={busy || !!pending || max === 0}
                onChange={(e) => setPoints(Number(e.target.value))}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n} disabled={!pending && n > max}>
                    {n} 點
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary full"
              disabled={
                busy || loading || (!pending && (max === 0 || points > max))
              }
            >
              {busy ? "處理中…" : pending ? "重試這次餵食" : "確認餵食"}
            </button>
            {max === 0 && !pending && (
              <p className="muted">
                {account.daily_remaining === 0
                  ? "今天已達餵食上限，明天再來看看。"
                  : "目前沒有可用點數，先和夥伴打聲招呼吧。"}
              </p>
            )}
          </form>
          <section className="point-history" aria-label="我的近期點數交易">
            <h2>我的近期點數交易</h2>
            <p className="muted small">最近 20 筆，只有你自己的獲得與花費。</p>
            {account.transactions.length === 0 ? (
              <p>尚無點數交易。</p>
            ) : (
              <ul className="score-list">
                {account.transactions.map((entry) => (
                  <li className="point-transaction" key={entry.id}>
                    <div className="score-record-top">
                      <strong>
                        {entry.kind === "award" ? "獲得點數" : "餵食吉祥物"}
                      </strong>
                      <strong>
                        {entry.points > 0 ? "+" : ""}
                        {entry.points} 點
                      </strong>
                    </div>
                    <time className="muted small" dateTime={entry.created_at}>
                      {new Date(entry.created_at).toLocaleString("zh-TW", {
                        timeZone: "Asia/Taipei",
                      })}
                      （台北）
                    </time>
                    {entry.source && (
                      <p>
                        {entry.source.is_deleted ? (
                          "來源已刪除，點數保留"
                        ) : (
                          <>
                            {entry.source.reason}
                            {entry.source.note && ` · ${entry.source.note}`}
                            {entry.source.is_modified &&
                              "（來源已修改，點數保留）"}
                          </>
                        )}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
