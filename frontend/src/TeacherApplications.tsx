import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

export const membershipStatuses: Record<string, string> = {
  pending: "等待審核",
  approved: "已加入",
  rejected: "已拒絕",
  removed: "已移除",
};

type Application = {
  id: number;
  cohort_name: string;
  homeroom_name: string;
  status: string;
};

export function TeacherApplications({
  onClassesChanged,
}: {
  onClassesChanged: () => Promise<void>;
}) {
  const [items, setItems] = useState<Application[]>([]);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    api<Application[]>("/teacher-applications/")
      .then((result) => {
        if (active) setItems(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function refresh(submit = false) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (submit) {
        const result = await api<Application>(
          "/teacher-applications/",
          "POST",
          { application_code: code.trim().toUpperCase() },
        );
        setNotice(
          `「${result.cohort_name}」：${membershipStatuses[result.status]}`,
        );
      }
      setItems(await api<Application[]>("/teacher-applications/"));
      await onClassesChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "無法更新申請，請再試一次。");
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!busy) void refresh(true);
  }
  return (
    <section className="roster-panel join-class" aria-label="加入班級">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">共同教學</p>
          <h2>加入班級</h2>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void refresh()}
        >
          更新申請狀態
        </button>
      </div>
      <p className="muted small">
        向導師取得教師申請碼，送出後等待審核。此代碼與學生登入碼不同。
      </p>
      <form onSubmit={submit} className="application-form">
        <label>
          輸入教師申請碼
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            maxLength={18}
            placeholder="T-…"
            autoComplete="off"
            disabled={busy}
          />
        </label>
        <button className="primary" disabled={busy}>
          {busy ? "處理中…" : "送出申請"}
        </button>
      </form>
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
      {items.length > 0 && (
        <ul className="membership-list">
          {items.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.cohort_name}</strong>
                <p className="muted small">導師：{item.homeroom_name}</p>
              </div>
              <span className="badge">{membershipStatuses[item.status]}</span>
            </li>
          ))}
        </ul>
      )}
      {items.some((item) => ["rejected", "removed"].includes(item.status)) && (
        <p className="muted small">
          已拒絕或移除的申請，可向導師取得目前有效碼後重新申請，需再次審核。
        </p>
      )}
    </section>
  );
}
