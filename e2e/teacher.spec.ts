import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const python = resolve(
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python",
);
const mailLink = (email: string, purpose: string) =>
  execFileSync(python, ["scripts/read-mail.py", email, purpose], {
    encoding: "utf8",
    windowsHide: true,
  }).trim();

test("teacher verifies, creates a cohort, updates its grade, resets password and stays isolated", async ({
  page,
  browser,
}) => {
  const email = `teacher-${Date.now()}@example.com`;
  const password = "Browser!Classroom2026";
  await page.goto("/#register");
  await page.getByLabel("顯示名稱").fill("林老師");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "建立帳號並寄送驗證信" }).click();
  await expect(page.getByRole("status")).toContainText("驗證信已寄出");
  await page.goto(mailLink(email, "verify"));
  await page.getByRole("button", { name: "確認驗證 Email" }).click();
  await expect(page.getByRole("status")).toContainText("驗證完成");
  await page.getByRole("link", { name: "返回登入" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await expect(
    page.getByRole("heading", { name: "我的班級", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "建立第一個班級" }).click();
  await page.getByLabel("班級名稱").fill("向日葵班");
  await page.getByLabel("入學年度").fill("2026");
  await page.getByRole("button", { name: "建立班級", exact: true }).click();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toBeVisible();
  await page.getByRole("button", { name: "編輯班級" }).click();
  await page.getByLabel("目前年級").selectOption("2");
  await page.getByRole("button", { name: "儲存變更" }).click();
  await expect(page.locator(".class-card")).toHaveCount(1);
  await expect(page.locator(".card-bottom")).toContainText("2 年級");
  await page.reload();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toBeVisible();
  await page.screenshot({
    path: ".local/classroom-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/classroom-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  const otherContext = await browser.newContext();
  const other = await otherContext.newPage();
  await other.goto("http://127.0.0.1:5173/#register");
  const otherEmail = `other-${Date.now()}@example.com`;
  await other.getByLabel("顯示名稱").fill("陳老師");
  await other.getByLabel("Email", { exact: true }).fill(otherEmail);
  await other.getByLabel("密碼", { exact: true }).fill(password);
  await other.getByRole("button", { name: "建立帳號並寄送驗證信" }).click();
  await expect(other.getByRole("status")).toBeVisible();
  await other.goto(mailLink(otherEmail, "verify"));
  await other.getByRole("button", { name: "確認驗證 Email" }).click();
  await expect(other.getByRole("status")).toContainText("驗證完成");
  await other.getByRole("link", { name: "返回登入" }).click();
  await other.getByLabel("Email", { exact: true }).fill(otherEmail);
  await other.getByLabel("密碼", { exact: true }).fill(password);
  await other.getByRole("button", { name: "登入班級日常" }).click();
  await expect(
    other.getByRole("button", { name: "建立第一個班級" }),
  ).toBeVisible();
  await expect(other.getByRole("heading", { name: "向日葵班" })).toHaveCount(0);
  await otherContext.close();

  await page.getByRole("button", { name: "登出", exact: true }).click();
  await page.getByRole("link", { name: "忘記密碼" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "寄送重設連結" }).click();
  await expect(page.getByRole("status")).toContainText("信件已寄出");
  // A teacher may open a reset link after signing back in while waiting for email.
  await page.getByRole("link", { name: "返回登入" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toBeVisible();
  const existingTab = await page.context().newPage();
  await existingTab.goto("/#classes");
  await expect(
    existingTab.getByRole("heading", { name: "向日葵班" }),
  ).toBeVisible();
  await page.goto(mailLink(email, "reset"));
  await page
    .getByLabel("新密碼", { exact: true })
    .fill("Changed!Classroom2026");
  await page.getByRole("button", { name: "更新密碼" }).click();
  await expect(page.getByRole("status")).toContainText("密碼已更新");
  await existingTab.getByRole("button", { name: "登出", exact: true }).click();
  await expect(
    existingTab.getByRole("button", { name: "登入班級日常" }),
  ).toBeVisible();
  await existingTab.close();
  await page.getByRole("link", { name: "返回登入" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill("Changed!Classroom2026");
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toBeVisible();

  // Permanent deletion is explicit, cancellable and still absent after reloading.
  await page.getByRole("button", { name: "編輯班級" }).click();
  await page.getByRole("button", { name: "永久刪除班級", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "永久刪除班級" });
  await expect(confirmation).toContainText("向日葵班");
  await expect(confirmation).toContainText("無法復原");
  await expect(confirmation).toContainText("教師帳號和其他班級不受影響");
  const remove = confirmation.getByRole("button", { name: "確認永久刪除" });
  await expect(remove).toBeDisabled();
  await confirmation.getByLabel("輸入完整班級名稱").fill("向日葵");
  await expect(remove).toBeDisabled();
  await confirmation.getByRole("button", { name: "取消" }).click();
  await expect(confirmation).not.toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toBeVisible();

  await page.getByRole("button", { name: "編輯班級" }).click();
  await page.getByRole("button", { name: "永久刪除班級", exact: true }).click();
  await confirmation.getByLabel("輸入完整班級名稱").fill("向日葵班");
  await expect(remove).toBeEnabled();

  // Another tab renamed the class: the stale confirmation must fail safely.
  const cohorts = await (await page.request.get("/api/classes/")).json();
  const csrf = await (await page.request.get("/api/csrf/")).json();
  const renamed = await page.request.patch(`/api/classes/${cohorts[0].id}/`, {
    headers: { "X-CSRFToken": csrf.csrfToken },
    data: { name: "向日葵二班" },
  });
  expect(renamed.ok()).toBe(true);
  await remove.click();
  await expect(confirmation.getByRole("alert")).toContainText(
    "請輸入目前完整班級名稱",
  );
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "取消" }).click();
  await page.reload();
  await expect(page.getByRole("heading", { name: "向日葵二班" })).toBeVisible();
  await page.getByRole("button", { name: "編輯班級" }).click();
  await page.getByRole("button", { name: "永久刪除班級", exact: true }).click();
  await confirmation.getByLabel("輸入完整班級名稱").fill("向日葵二班");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: ".local/delete-class-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/delete-class-mobile.png",
    fullPage: true,
  });
  expect(
    await confirmation.evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await remove.click();
  await expect(confirmation).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("已永久刪除");
  await expect(page.locator(".class-card")).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "建立第一個班級" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toHaveCount(0);
});
