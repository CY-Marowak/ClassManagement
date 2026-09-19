import { useEffect, useState } from "react";
import { api, type Cohort } from "./api";
import { membershipStatuses } from "./TeacherApplications";
import { TeacherAuditHistory } from "./TeacherAuditHistory";

type Member = { id: number; name: string; status: string; revision: number };
type Management = { application_code: string; members: Member[] };

export function TeacherManagement({
  cohort,
  onBack,
}: {
  cohort: Cohort;
  onBack: () => void;
}) {
  const [data, setData] = useState<Management | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<Member | "rotate" | null>(null);
  const [history, setHistory] = useState(false);
  const [revision, setRevision] = useState(0);
  const base = `/classes/${cohort.id}/`;
  useEffect(() => {
    let active = true;
    api<Management>(base + "teachers/")
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  async function run(operation?: () => Promise<unknown>, message = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (operation) await operation();
      setConfirm(null);
      setData(await api<Management>(base + "teachers/"));
      setRevision((n) => n + 1);
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗，請重新整理後再試。");
      setData(null);
      setConfirm(null);
      setHistory(false);
    } finally {
      setBusy(false);
    }
  }
  const decide = (member: Member, action: string) =>
    run(
      () =>
        api(base + `teachers/${member.id}/`, "POST", {
          action,
          revision: member.revision,
        }),
      "教師狀態已更新。",
    );
  return (
    <>
      <button className="text-button" onClick={onBack} disabled={busy}>
        ← 返回我的班級
      </button>
      <header className="page-title">
        <div>
          <p className="eyebrow">班級成員</p>
          <h1>{cohort.name} · 教師管理</h1>
          <p className="muted">審核共同教師，管理班級存取。</p>
        </div>
      </header>
      <div className="actions">
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void run()}
        >
          重新整理教師
        </button>
      </div>
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
      {!data && !error && <p role="status">正在載入教師…</p>}
      {data && (
        <>
          <section className="roster-panel" aria-label="教師申請代碼">
            <h2>邀請共同教師</h2>
            <p className="muted small">
              分享給要加入的教師。送出申請後，仍需由你批准。
            </p>
            <label>
              教師申請碼
              <input
                className="teacher-code"
                readOnly
                value={data.application_code}
                onFocus={(e) => e.target.select()}
              />
            </label>
            <p className="muted small">
              重產後舊碼立即失效，待審申請、已加入教師與學生登入碼都保持不變。
            </p>
            <button
              className="secondary"
              disabled={busy || !!confirm}
              onClick={() => setConfirm("rotate")}
            >
              重產申請碼
            </button>
          </section>
          {confirm && (
            <section
              className="roster-panel delete-warning"
              aria-label="確認教師操作"
            >
              <h2>
                {confirm === "rotate"
                  ? "重產申請碼？"
                  : `移除 ${confirm.name}？`}
              </h2>
              <p>
                {confirm === "rotate"
                  ? "舊碼將無法送出申請；既有待審申請保留。請將新碼分享給需要加入的教師。"
                  : "立即撤銷這位教師的班級存取權，既有歷史保留。教師帳號及其他班級不受影響。"}
              </p>
              <div className="actions">
                <button
                  className="secondary"
                  autoFocus
                  disabled={busy}
                  onClick={() => setConfirm(null)}
                >
                  取消
                </button>
                <button
                  className="danger-button"
                  disabled={busy}
                  onClick={() => {
                    if (confirm === "rotate")
                      void run(
                        () =>
                          api(base + "teacher-code/", "POST", {
                            application_code: data.application_code,
                          }),
                        "教師申請碼已更新。",
                      );
                    else void decide(confirm, "remove");
                  }}
                >
                  {confirm === "rotate" ? "確認重產申請碼" : "確認移除"}
                </button>
              </div>
            </section>
          )}
          <section className="roster-panel" aria-label="教師成員">
            <h2>共同教師與申請</h2>
            {data.members.length ? (
              <ul className="membership-list">
                {data.members.map((member) => (
                  <li key={member.id}>
                    <div>
                      <strong>{member.name}</strong>
                      <p className="muted small">
                        成員 #{member.id} · {membershipStatuses[member.status]}
                      </p>
                    </div>
                    <div className="actions">
                      {member.status === "pending" && (
                        <>
                          <button
                            className="secondary"
                            disabled={busy || !!confirm}
                            onClick={() => void decide(member, "reject")}
                          >
                            拒絕
                          </button>
                          <button
                            className="primary"
                            disabled={busy || !!confirm}
                            onClick={() => void decide(member, "approve")}
                          >
                            批准
                          </button>
                        </>
                      )}
                      {member.status === "approved" && (
                        <button
                          className="secondary danger-text"
                          disabled={busy || !!confirm}
                          onClick={() => setConfirm(member)}
                        >
                          移除
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                尚無教師申請。分享上方代碼，邀請共同教學。
              </p>
            )}
          </section>
          <button
            className="secondary"
            aria-expanded={history}
            onClick={() => setHistory(!history)}
          >
            教師操作紀錄
          </button>
          {history && (
            <TeacherAuditHistory key={revision} cohortId={cohort.id} />
          )}
        </>
      )}
    </>
  );
}
