export type Teacher = {
  id: number;
  display_name: string;
  email: string;
  email_verified: boolean;
};
export type Cohort = {
  id: number;
  name: string;
  entry_year: number;
  current_grade: number;
  role: string;
};
export type Notice = { detail: string };

const fieldNames: Record<string, string> = {
  email: "Email",
  password: "密碼",
  display_name: "顯示名稱",
  name: "班級名稱",
  entry_year: "入學年度",
  current_grade: "目前年級",
  token: "驗證連結",
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
