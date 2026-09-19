export type Teacher = {
  account_type: "teacher";
  id: number;
  display_name: string;
  email: string;
  email_verified: boolean;
};
export type Cohort = {
  student_login_code: string;
  id: number;
  name: string;
  entry_year: number;
  current_grade: number;
  role: string;
};
export type Notice = { detail: string };
export type StudentSession = {
  account_type: "student";
  must_change_password: boolean;
};
export type Identity = Teacher | StudentSession;
export type Student = {
  id: number;
  name: string;
  seat_number: number;
  student_number: string;
  avatar: "cat" | "dog" | "rabbit";
};
export type StudentProfile = Student & { cohort: { id: number; name: string } };

const fieldNames: Record<string, string> = {
  email: "Email",
  password: "密碼",
  display_name: "顯示名稱",
  name: "名稱",
  seat_number: "座號",
  entry_year: "入學年度",
  current_grade: "目前年級",
  token: "驗證連結",
  confirmation_name: "確認班級名稱",
  confirmation_student_number: "確認學號",
  class_code: "班級登入碼",
  application_code: "教師申請碼",
  student_number: "學號",
  text: "名單",
};

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (method !== "GET") {
    const csrf = await fetch("/api/csrf/", { credentials: "same-origin" });
    if (!csrf.ok) throw new Error("目前無法連線，請稍後再試。");
    headers["X-CSRFToken"] = (await csrf.json()).csrfToken;
  }
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "服務暫時無法使用，請稍後再試。" }));
  if (!response.ok) {
    const message =
      data.detail ||
      Object.entries(data)
        .map(
          ([key, value]) =>
            `${fieldNames[key] || key}：${Array.isArray(value) ? value.join(" ") : value}`,
        )
        .join("；");
    throw new Error(message);
  }
  return data as T;
}
