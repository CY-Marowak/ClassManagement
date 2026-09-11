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
  await page.goto(mailLink(email, "reset"));
  await page
    .getByLabel("新密碼", { exact: true })
    .fill("Changed!Classroom2026");
  await page.getByRole("button", { name: "更新密碼" }).click();
  await expect(page.getByRole("status")).toContainText("密碼已更新");
  await page.getByRole("link", { name: "返回登入" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill("Changed!Classroom2026");
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await expect(page.getByRole("heading", { name: "向日葵班" })).toBeVisible();
});
