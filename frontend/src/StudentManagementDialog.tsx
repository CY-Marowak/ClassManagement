import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Notice, type Student } from "./api";

export function StudentManagementDialog({
  student,
  endpoint,
  mode,
  onCancel,
  onComplete,
}: {
  student: Student;
  endpoint: string;
  mode: "edit" | "reset";
  onCancel: () => void;
  onComplete: (student: Student, message: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editing = mode === "edit";
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const values = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      if (editing) {
        const saved = await api<Student>(`${endpoint}${student.id}/`, "PATCH", {
          name: String(values.get("name")),
          seat_number: Number(values.get("seat_number")),
          student_number: String(values.get("student_number")),
        });
        onComplete(saved, "學生資料已儲存。");
      } else {
        const result = await api<Notice>(
          `${endpoint}${student.id}/reset-password/`,
          "POST",
        );
        onComplete(student, result.detail);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="student-dialog"
      aria-labelledby="student-dialog-title"
      aria-describedby="student-dialog-description"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <form onSubmit={submit}>
        <p className="eyebrow">學生帳號管理</p>
        <h2 id="student-dialog-title">
          {editing ? "修改學生資料" : "重設學生密碼"}
        </h2>
        <p className="student-target">
          {student.seat_number} 號 · <strong>{student.name}</strong> ·{" "}
          {student.student_number}
        </p>
        <p
          id="student-dialog-description"
          className={editing ? "muted small" : "delete-warning"}
        >
          {editing
            ? "修改學號後，以新學號登入，密碼維持原樣；角色與歷史紀錄保留。尚未改過密碼的學生仍使用原初始密碼，必要時請另行重設。"
            : "確認後，密碼會重設為目前學號，所有原登入立即失效。學生重新登入後必須設定新密碼。"}
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {editing && (
          <>
            <label>
              姓名
              <input
                name="name"
                defaultValue={student.name}
                maxLength={80}
                required
                autoFocus
                disabled={busy}
              />
            </label>
            <div className="form-row">
              <label>
                座號
                <input
                  name="seat_number"
                  type="number"
                  min={1}
                  max={9999}
                  step={1}
                  defaultValue={student.seat_number}
                  required
                  disabled={busy}
                />
              </label>
              <label>
                學號
                <input
                  name="student_number"
                  defaultValue={student.student_number}
                  maxLength={64}
                  pattern="\S{1,64}"
                  required
                  disabled={busy}
                />
              </label>
            </div>
          </>
        )}
        <div className="actions">
          <button
            className="secondary"
            type="button"
            onClick={onCancel}
            disabled={busy}
            autoFocus={!editing}
          >
            取消
          </button>
          <button
            className={editing ? "primary" : "danger-button"}
            disabled={busy}
          >
            {busy ? "處理中…" : editing ? "儲存修改" : "確認重設密碼"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
