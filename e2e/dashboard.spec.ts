import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("homeroom dashboard keeps import tasks and opens their work directly", async ({
  page,
}) => {
  test.setTimeout(60000);
  const email = `dashboard-${Date.now()}@example.com`;
  await page.goto("/#login");
  async function post(path: string, data: unknown) {
    const { csrfToken } = await (await page.request.get("/api/csrf/")).json();
    const response = await page.request.post(`/api${path}`, {
      headers: { "X-CSRFToken": csrfToken },
      data,
    });
    expect(response.ok()).toBe(true);
    return response.json();
  }
  await post("/auth/register/", {
    email,
    password: "Dashboard!Teacher2026",
    display_name: "首頁導師",
  });
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    { encoding: "utf8", windowsHide: true },
  ).trim();
  await post("/auth/verify/", {
    token: new URLSearchParams(new URL(link).hash.split("?")[1]).get("token"),
  });
  await post("/auth/login/", { email, password: "Dashboard!Teacher2026" });
  const cohort = await post("/classes/", {
    name: "首頁工作班",
    entry_year: 2026,
    current_grade: 1,
  });
  await post(`/classes/${cohort.id}/students/`, {
    text: "1\t小明\t001\n2\t小美\n3\t小華",
  });
  await page.reload();
  await page.getByRole("button", { name: "工作首頁", exact: true }).click();
  await expect(page.getByRole("button", { name: /待修正學生/ })).toContainText(
    "2",
  );
  await page.getByRole("button", { name: /待修正學生/ }).click();
  await expect(page.locator(".import-issue")).toHaveCount(2);
  await page.reload();
  await page.getByRole("button", { name: "工作首頁", exact: true }).click();
  await page.getByRole("button", { name: /待修正學生/ }).click();
  const first = page.locator(".import-issue").first();
  await first.getByRole("button", { name: "修正這列" }).click();
  await first.getByLabel("學號", { exact: true }).fill("001");
  await first.getByRole("button", { name: "修正並重試" }).click();
  await expect(page.getByRole("alert")).toContainText("學號已存在");
  await page.getByRole("button", { name: "重新整理待修正名單" }).click();
  await first.getByRole("button", { name: "修正這列" }).click();
  await expect(first.getByLabel("學號", { exact: true })).toHaveValue("001");
  await expect(first.getByText("原始資料：", { exact: false })).toHaveText(
    "原始資料：2 │ 小美",
  );
  await first.getByLabel("學號", { exact: true }).fill("002");
  await first.getByRole("button", { name: "修正並重試" }).click();
  await expect(page.locator(".import-issue")).toHaveCount(1);
  await page.getByRole("button", { name: "忽略這列" }).click();
  await page.getByRole("button", { name: "取消忽略" }).click();
  await expect(page.locator(".import-issue")).toHaveCount(1);
  await page.getByRole("button", { name: "忽略這列" }).click();
  await page.getByRole("button", { name: "確認忽略" }).click();
  await expect(
    page.getByRole("heading", { name: "沒有待修正資料" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "返回工作首頁", exact: false })
    .click();
  await expect(page.getByRole("button", { name: /待修正學生/ })).toContainText(
    "0",
  );
  await page.getByRole("button", { name: "開始記分" }).click();
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption({ label: "2 號 · 小美（總分 0）" });
  await page.getByLabel("原因模板").selectOption("other");
  await page.getByRole("button", { name: "送出記分", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已記錄" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "返回工作首頁", exact: false })
    .click();
  await expect(page.getByRole("button", { name: /待補原因/ })).toContainText(
    "1",
  );
  await page.getByRole("button", { name: /待補原因/ }).click();
  await page.getByRole("checkbox").check();
  await page.getByLabel("統一補充原因").fill("協助同學");
  await page.getByRole("button", { name: "儲存原因" }).click();
  await expect(
    page.getByText("目前沒有可補的原因。", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "返回工作首頁", exact: false })
    .click();
  await expect(page.getByRole("button", { name: /待補原因/ })).toContainText(
    "0",
  );
  await page.screenshot({
    path: ".local/12-dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/12-dashboard-mobile.png",
    fullPage: true,
  });
});
