import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Notice, type Student } from "./api";

export function DeleteStudentDialog({
  student,
  endpoint,
  onCancel,
  onDeleted,
}: {
  student: Student;
  endpoint: string;
  onCancel: () => void;
  onDeleted: (student: Student, message: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || confirmation !== student.student_number) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<Notice>(`${endpoint}${student.id}/`, "DELETE", {
        confirmation_student_number: confirmation,
      });
      onDeleted(student, result.detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "刪除失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="student-dialog"
      aria-labelledby="delete-student-title"
      aria-describedby="delete-student-warning"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <form onSubmit={submit}>
        <p className="eyebrow danger-text">危險操作</p>
        <h2 id="delete-student-title">永久刪除學生</h2>
        <p className="student-target">
          {student.seat_number} 號 · <strong>{student.name}</strong> · 學號{" "}
          {student.student_number}
        </p>
        <div id="delete-student-warning" className="delete-warning">
          <strong>學生帳號及全部歷史會永久刪除，無法復原。</strong>
          <p>
            包含學生資料、固定角色及建立、修改、重設密碼的操作紀錄。所有原登入立即失效。
          </p>
          <p>
            其他學生及班級不受影響。重新匯入只會建立新帳號，不會恢復舊資料。
          </p>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <label>
          輸入完整學號
          <input
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            maxLength={64}
            autoComplete="off"
            required
            disabled={busy}
          />
        </label>
        <div className="actions">
          <button
            type="button"
            className="secondary"
            onClick={onCancel}
            disabled={busy}
            autoFocus
          >
            取消
          </button>
          <button
            className="danger-button"
            disabled={busy || confirmation !== student.student_number}
          >
            {busy ? "刪除中…" : "確認永久刪除學生"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
