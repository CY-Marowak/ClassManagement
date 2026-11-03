import { test, expect, type Page, type Download } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

async function post(page: Page, path: string, data: unknown) {
  const { csrfToken } = await (await page.request.get("/api/csrf/")).json();
  const response = await page.request.post(`/api${path}`, {
    headers: { "X-CSRFToken": csrfToken },
    data,
  });
  expect(response.ok()).toBe(true);
  return response.json();
}
async function csv(download: Download) {
  expect(await download.failure()).toBeNull();
  return readFileSync((await download.path())!, "utf8");
}
test("students browse full personal history and homeroom exports only selected class records", async ({
  page,
}) => {
  test.setTimeout(120000);
  const email = `history-${Date.now()}@example.com`;
  const password = "Teacher!History2026";
  await page.goto("/#login");
  await post(page, "/auth/register/", {
    email,
    password,
    display_name: "明細導師",
  });
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    { encoding: "utf8", windowsHide: true },
  ).trim();
  await post(page, "/auth/verify/", {
    token: new URLSearchParams(new URL(link).hash.split("?")[1]).get("token"),
  });
  await post(page, "/auth/login/", { email, password });
  const cohort = await post(page, "/classes/", {
    name: "明細測試班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(page, base + "students/", {
    text: "1\t明細同學\t001\n2\t其他同學\t002",
  });
  const students = await (
    await page.request.get(`/api${base}students/`)
  ).json();
  for (let index = 0; index < 29; index++) {
    const record = await post(page, base + "scores/", {
      student_id: students[index === 28 ? 1 : 0].id,
      kind: "positive",
      score: 1,
      template: "other",
      note: `明細記錄${index}`,
      request_id: crypto.randomUUID(),
    });
    if (index === 0 || index === 28)
      await post(page, base + "point-awards/", {
        request_id: crypto.randomUUID(),
        items: [{ record_id: record.id, revision: 1, points: 30 }],
      });
  }
  execFileSync(
    resolve(".venv/Scripts/python.exe"),
    [
      "backend/manage.py",
      "shell",
      "-c",
      `from core.models import ScoreRecord; from datetime import datetime, timezone; ScoreRecord.objects.filter(cohort_id=${cohort.id}).update(created_at=datetime(2026,11,2,16,tzinfo=timezone.utc))`,
    ],
    { env: { ...process.env, CM_DEBUG: "1" }, windowsHide: true },
  );
  await page.reload();
  await page.getByRole("button", { name: "工作首頁", exact: true }).click();
  await page
    .getByRole("button", { name: "明細與匯出", exact: true })
    .click();
  await expect(
    page.getByText("共 29 筆 · 第 1 頁 · 由新到舊", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "學生", exact: true })
    .selectOption(String(students[0].id));
  await page.getByLabel("起日", { exact: true }).fill("2026-11-03");
  await page.getByLabel("迄日", { exact: true }).fill("2026-11-03");
  const exportButton = page.getByRole("button", { name: "下載目前篩選的 CSV" });
  await expect(exportButton).toBeDisabled();
  await page.getByRole("button", { name: "套用篩選" }).click();
  await expect(
    page.getByText("共 28 筆 · 第 1 頁 · 由新到舊", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一頁", exact: true }).click();
  await expect(page.locator(".history-record")).toHaveCount(3);
  let pendingDownload = page.waitForEvent("download");
  await exportButton.click();
  const teacherCsv = await csv(await pendingDownload);
  expect(teacherCsv).toContain("學號");
  expect(teacherCsv).toContain("001");
  expect(teacherCsv).not.toContain("其他同學");
  expect(teacherCsv.trim().split("\r\n")).toHaveLength(29);
  expect(teacherCsv).toContain("2026-11-03 00:00:00");
  await page.screenshot({
    path: ".local/v2-06-teacher-desktop.png",
    fullPage: true,
  });
  await post(page, "/auth/logout/", {});
  await post(page, "/student/login/", {
    class_code: cohort.student_login_code,
    student_number: "001",
    password: "001",
  });
  await post(page, "/student/change-password/", {
    password: "Student!History2026",
  });
  await post(page, "/student/mascot/", {
    points: 2,
    request_id: crypto.randomUUID(),
  });
  const roles = await (await page.request.get("/api/student/roles/")).json();
  const role = roles.catalog.find(
    (item: { id: string }) => !roles.owned.includes(item.id),
  );
  await post(page, "/student/roles/purchases/", {
    role: role.id,
    request_id: crypto.randomUUID(),
  });
  await page.reload();
  await page
    .getByRole("button", { name: "明細與匯出", exact: true })
    .click();
  await expect(
    page.getByText("共 28 筆 · 第 1 頁 · 由新到舊", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一頁", exact: true }).click();
  await expect(page.locator(".history-record")).toHaveCount(3);
  pendingDownload = page.waitForEvent("download");
  await exportButton.click();
  const studentCsv = await csv(await pendingDownload);
  expect(studentCsv).not.toContain("學號");
  expect(studentCsv.trim().split("\r\n")).toHaveLength(29);
  await page.getByRole("button", { name: "點數明細", exact: true }).click();
  await expect(page.locator(".history-record")).toHaveCount(3);
  await page
    .getByRole("combobox", { name: "交易類型", exact: true })
    .selectOption("purchase");
  await page.getByRole("button", { name: "套用篩選" }).click();
  await expect(page.locator(".history-record")).toHaveCount(1);
  await expect(page.locator(".history-record")).toContainText(role.name);
  pendingDownload = page.waitForEvent("download");
  await exportButton.click();
  const purchaseCsv = await csv(await pendingDownload);
  expect(purchaseCsv).toContain("-20");
  expect(purchaseCsv).toContain(role.name);
  expect(purchaseCsv).not.toContain("餵食班級吉祥物");
  await page.setViewportSize({ width: 320, height: 850 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: ".local/v2-06-student-mobile.png",
    fullPage: true,
  });
  await page.getByLabel("迄日", { exact: true }).fill("2000-01-01");
  await page.getByRole("button", { name: "套用篩選" }).click();
  await expect(
    page.getByText("沒有符合條件的紀錄；仍可下載欄位表頭。", { exact: true }),
  ).toBeVisible();
  pendingDownload = page.waitForEvent("download");
  await exportButton.click();
  expect((await csv(await pendingDownload)).trim().split("\r\n")).toHaveLength(
    1,
  );
  await page.route("**/history/points/export/**", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "登入已失效，請重新登入。" }),
    }),
  );
  await exportButton.click();
  await expect(page.getByRole("alert")).toContainText("登入已失效");
  await expect(exportButton).toBeDisabled();
  await expect(page.locator(".history-record")).toHaveCount(0);
});
