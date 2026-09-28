import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.use({ actionTimeout: 10000 });

async function post(page: Page, path: string, data: unknown) {
  const { csrfToken } = await (await page.request.get("/api/csrf/")).json();
  const response = await page.request.post(`/api${path}`, {
    headers: { "X-CSRFToken": csrfToken },
    data,
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

test("student sees points, feeds voluntarily, safely retries and shares class growth", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  const email = `mascot-${Date.now()}@example.com`;
  const password = "Teacher!Mascot2026";
  await page.goto("/#login");
  await post(page, "/auth/register/", {
    email,
    password,
    display_name: "吉祥物導師",
  });
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    { encoding: "utf8", windowsHide: true },
  ).trim();
  const token = new URLSearchParams(new URL(link).hash.split("?")[1]).get(
    "token",
  );
  await post(page, "/auth/verify/", { token });
  await post(page, "/auth/login/", { email, password });
  const cohort = await post(page, "/classes/", {
    name: "共同成長班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(page, base + "students/", { text: "1\t小明\t001\n2\t小美\t002" });
  const students = await (
    await page.request.get(`/api${base}students/`)
  ).json();
  const record = await post(page, base + "scores/", {
    student_id: students[0].id,
    kind: "positive",
    score: 3,
    template: "helping",
    note: "整理教室",
    request_id: crypto.randomUUID(),
  });
  await post(page, base + "point-awards/", {
    request_id: crypto.randomUUID(),
    items: [{ record_id: record.id, revision: 1, points: 8 }],
  });
  const context = await browser.newContext();
  const student = await context.newPage();
  await student.goto(`/#student-login?class=${cohort.student_login_code}`);
  await student.getByLabel("學號", { exact: true }).fill("001");
  await student.getByLabel("密碼", { exact: true }).fill("001");
  await student.getByRole("button", { name: "學生登入", exact: true }).click();
  await student
    .getByLabel("新密碼", { exact: true })
    .fill("Student!Mascot2026");
  await student.getByLabel("確認新密碼").fill("Student!Mascot2026");
  await student.getByRole("button", { name: "儲存密碼並進入班級" }).click();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toContainText("可用點數 8");
  await expect(student.locator(".score-total")).toHaveText("累積分數 3");
  await student.getByRole("button", { name: "餵食班級吉祥物" }).click();
  await expect(
    student.getByRole("heading", { name: "班級吉祥物", exact: true }),
  ).toBeVisible();
  await expect(
    student.getByText("距下一級還需 100 exp", { exact: true }),
  ).toBeVisible();
  await expect(student.locator(".point-transaction")).toHaveCount(1);
  await student.getByLabel("餵食點數").selectOption("2");
  await student.route(
    "**/api/student/mascot/",
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await student.getByRole("button", { name: "確認餵食", exact: true }).click();
  await expect(student.getByRole("alert")).toBeVisible();
  await student.reload();
  await student.getByRole("button", { name: "餵食班級吉祥物" }).click();
  await student
    .getByRole("button", { name: "重試這次餵食", exact: true })
    .click();
  await expect(student.getByText("可用點數 6", { exact: true })).toBeVisible();
  await expect(
    student.getByText("今日還可餵 3 點", { exact: true }),
  ).toBeVisible();
  await expect(student.locator(".point-transaction")).toHaveCount(2);
  await expect(
    student.getByText("累積總餵食量 2 exp", { exact: true }),
  ).toBeVisible();
  await student.getByLabel("餵食點數").selectOption("3");
  await student.getByRole("button", { name: "確認餵食", exact: true }).click();
  await expect(
    student.getByText("今日還可餵 0 點", { exact: true }),
  ).toBeVisible();
  await expect(
    student.getByRole("button", { name: "確認餵食", exact: true }),
  ).toBeDisabled();
  await student.screenshot({
    path: ".local/09-mascot-desktop.png",
    fullPage: true,
  });
  await student.setViewportSize({ width: 390, height: 844 });
  await student.screenshot({
    path: ".local/09-mascot-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await student.getByRole("button", { name: "返回我的頁面" }).click();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toContainText("可用點數 3");
  await expect(student.locator(".score-total")).toHaveText("累積分數 3");
  await student.screenshot({
    path: ".local/09-home-mobile.png",
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("button", { name: "班級吉祥物", exact: true }).click();
  await expect(
    page.getByText("累積總餵食量 5 exp", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "確認餵食", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".point-transaction")).toHaveCount(0);
  const emptyContext = await browser.newContext();
  const empty = await emptyContext.newPage();
  await empty.goto("/#student-login");
  await post(empty, "/student/login/", {
    class_code: cohort.student_login_code,
    student_number: "002",
    password: "002",
  });
  await post(empty, "/student/change-password/", {
    password: "Student!Mascot2026",
  });
  await empty.reload();
  await empty.getByRole("button", { name: "餵食班級吉祥物" }).click();
  await expect(
    empty.getByText("累積總餵食量 5 exp", { exact: true }),
  ).toBeVisible();
  await expect(
    empty.getByText("尚無點數交易。", { exact: true }),
  ).toBeVisible();
  await expect(
    empty.getByRole("button", { name: "確認餵食", exact: true }),
  ).toBeDisabled();
  await expect(empty.getByText("整理教室", { exact: true })).toHaveCount(0);
  await emptyContext.close();
  await context.close();
});
