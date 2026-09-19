import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

async function registerAndLogin(page: Page, name: string, email: string) {
  await page.goto("/#login");
  const csrf = await (await page.request.get("/api/csrf/")).json();
  const headers = { "X-CSRFToken": csrf.csrfToken };
  const password = "Together!Classroom2026";
  expect(
    (
      await page.request.post("/api/auth/register/", {
        headers,
        data: { email, display_name: name, password },
      })
    ).ok(),
  ).toBe(true);
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    {
      encoding: "utf8",
      windowsHide: true,
    },
  ).trim();
  const token = new URLSearchParams(new URL(link).hash.split("?")[1]).get(
    "token",
  );
  expect(
    (
      await page.request.post("/api/auth/verify/", { headers, data: { token } })
    ).ok(),
  ).toBe(true);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await expect(
    page.getByRole("heading", { name: "我的班級", exact: true }),
  ).toBeVisible();
}

test("co-teacher applies, owner rotates code and reviews, removal requires a fresh application", async ({
  page,
  browser,
}) => {
  const suffix = Date.now();
  await registerAndLogin(page, "導師林", `member-owner-${suffix}@example.com`);
  await page.getByRole("button", { name: "建立第一個班級" }).click();
  await page.getByLabel("班級名稱").fill("共同教學班");
  await page.getByRole("button", { name: "建立班級", exact: true }).click();
  await page.getByRole("button", { name: "教師管理", exact: true }).click();
  const code = await page
    .getByLabel("教師申請碼", { exact: true })
    .inputValue();
  const colleagueContext = await browser.newContext();
  const colleague = await colleagueContext.newPage();
  await registerAndLogin(
    colleague,
    "共同陳",
    `member-colleague-${suffix}@example.com`,
  );
  await colleague.getByLabel("輸入教師申請碼").fill(code);
  await colleague.getByRole("button", { name: "送出申請" }).click();
  const applications = colleague.getByRole("region", { name: "加入班級" });
  await expect(applications).toContainText("等待審核");
  await expect(applications).toContainText("共同教學班");
  await expect(applications).toContainText("導師林");
  await expect(
    colleague.getByRole("button", { name: "學生名單", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "重新整理教師" }).click();
  await expect(page.getByRole("region", { name: "教師成員" })).toContainText(
    "共同陳",
  );
  await page.getByRole("button", { name: "重產申請碼", exact: true }).click();
  await page
    .getByRole("button", { name: "確認重產申請碼", exact: true })
    .click();
  await expect(page.getByLabel("教師申請碼", { exact: true })).not.toHaveValue(
    code,
  );
  const newCode = await page
    .getByLabel("教師申請碼", { exact: true })
    .inputValue();
  await page.getByRole("button", { name: "批准", exact: true }).click();
  await colleague.getByRole("button", { name: "更新申請狀態" }).click();
  await expect(colleague.locator(".class-card")).toContainText("共同教學班");
  await expect(
    colleague.getByRole("button", { name: "教師管理", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "移除", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "確認教師操作" }),
  ).toContainText("歷史保留");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("region", { name: "教師成員" })).toContainText(
    "已加入",
  );
  await page.getByRole("button", { name: "移除", exact: true }).click();
  await page.getByRole("button", { name: "確認移除", exact: true }).click();
  await colleague.getByRole("button", { name: "更新申請狀態" }).click();
  await expect(colleague.locator(".class-card")).toHaveCount(0);
  await expect(applications).toContainText("已移除");
  await colleague.getByLabel("輸入教師申請碼").fill(code);
  await colleague.getByRole("button", { name: "送出申請" }).click();
  await expect(applications.getByRole("alert")).toBeVisible();
  await colleague.getByLabel("輸入教師申請碼").fill(newCode);
  await colleague.getByRole("button", { name: "送出申請" }).click();
  await expect(applications).toContainText("等待審核");
  await expect(colleague.locator(".class-card")).toHaveCount(0);
  await page.getByRole("button", { name: "重新整理教師" }).click();
  await page.getByRole("button", { name: "拒絕", exact: true }).click();
  await colleague.getByRole("button", { name: "更新申請狀態" }).click();
  await expect(applications).toContainText("已拒絕");
  await page.getByRole("button", { name: "教師操作紀錄", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "教師操作紀錄" }),
  ).toContainText("移除共同教師");
  await page.screenshot({
    path: ".local/teachers-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".local/teachers-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await colleagueContext.close();
});
