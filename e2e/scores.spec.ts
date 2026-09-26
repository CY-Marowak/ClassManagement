import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.use({ actionTimeout: 10000 });

test("batch scoring and pending reasons stay separate and retry safely", async ({
  page,
}) => {
  test.setTimeout(90000);
  await teacher(page, `batch-${Date.now()}@example.com`, "批次導師");
  const cohort = await post(page, "/classes/", {
    name: "批次班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(page, base + "students/", { text: "1\t小明\t001\n2\t小美\t002" });
  await page.reload();
  await page.getByRole("button", { name: "記分", exact: true }).click();
  await page.getByLabel("記分模式").selectOption("batch");
  await page.getByRole("button", { name: "全選學生", exact: true }).click();
  await expect(page.getByText("已選 2 位學生", { exact: true })).toBeVisible();
  await page.getByLabel("原因模板").selectOption("other");
  await page.getByLabel("分數", { exact: true }).fill("2");
  await page.route(
    `**/api${base}score-batches/`,
    async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "送出批次記分" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "送出批次記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText(
    "已記錄 2 位學生",
  );
  await expect(
    page.getByRole("region", { name: "分數紀錄", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  const history = page.getByRole("region", { name: "分數紀錄", exact: true });
  await expect(history).toContainText("共 2 筆");
  await expect(history.getByText(/同批記分/)).toHaveCount(2);
  await page.getByRole("button", { name: "整理待補原因" }).click();
  await expect(
    page.getByRole("heading", { name: "待補原因", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "全選本頁" }).click();
  await page.getByLabel("統一補充原因").fill("共同協助整理教室");
  await page.screenshot({
    path: ".local/06-pending-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/06-pending-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.route(
    `**/api${base}pending-reasons/`,
    async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "儲存原因" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "儲存原因" }).click();
  await expect(page.getByRole("status")).toContainText("已補齊 2 筆原因");
  await expect(page.getByText("目前沒有可補的原因。")).toBeVisible();
  await page.getByRole("button", { name: "← 返回分數紀錄" }).click();
  await expect(
    history.getByText("共同協助整理教室", { exact: true }),
  ).toHaveCount(2);
  await expect(history.getByText("待補原因", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "← 返回記分" }).click();
  await expect(page.getByLabel("記分模式")).toHaveValue("batch");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".local/06-batch-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: ".local/06-batch-desktop.png",
    fullPage: true,
  });
});

async function post(page: Page, path: string, data: unknown) {
  const { csrfToken } = await (await page.request.get("/api/csrf/")).json();
  const response = await page.request.post(`/api${path}`, {
    headers: { "X-CSRFToken": csrfToken },
    data,
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function teacher(page: Page, email: string, name: string) {
  await page.goto("/#login");
  const password = "Teacher!Scoring2026";
  await post(page, "/auth/register/", { email, password, display_name: name });
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    { encoding: "utf8", windowsHide: true },
  ).trim();
  const token = new URLSearchParams(new URL(link).hash.split("?")[1]).get(
    "token",
  );
  await post(page, "/auth/verify/", { token });
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await expect(
    page.getByRole("heading", { name: "我的班級", exact: true }),
  ).toBeVisible();
}

test("teachers record scores including zero; retry is safe; students see only their own scores", async ({
  page,
  browser,
}) => {
  test.setTimeout(120000);
  const suffix = Date.now();
  await teacher(page, `score-owner-${suffix}@example.com`, "記分導師");
  const cohort = await post(page, "/classes/", {
    name: "記分示範班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(page, base + "students/", { text: "1\t小明\t001\n2\t小美\t002" });
  const roster = await (await page.request.get(`/api${base}students/`)).json();
  const code = (await (await page.request.get(`/api${base}teachers/`)).json())
    .application_code;
  const coContext = await browser.newContext();
  const co = await coContext.newPage();
  await teacher(co, `score-co-${suffix}@example.com`, "共同教師陳");
  const application = await post(co, "/teacher-applications/", {
    application_code: code,
  });
  await post(page, base + `teachers/${application.id}/`, {
    action: "approve",
    revision: 1,
  });
  await co.reload();
  await co.getByRole("button", { name: "記分", exact: true }).click();
  await expect(co.getByRole("heading", { name: "新增一筆記分" })).toBeVisible();
  await expect(co.getByLabel("查看紀錄")).toHaveCount(0);
  await expect(
    co.getByRole("region", { name: "分數紀錄", exact: true }),
  ).toHaveCount(0);
  await co
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[0].id));
  await co.getByLabel("分數", { exact: true }).fill("3");
  await co.getByLabel("補充原因（選填）").fill("主動分享解題方法");
  await co.getByRole("button", { name: "送出記分" }).click();
  await expect(co.locator('.notice[role="status"]')).toContainText(
    "未發放點數",
  );
  await co.getByRole("button", { name: "查看分數紀錄 →" }).click();
  await expect(
    co.getByRole("heading", { name: "分數紀錄", exact: true }),
  ).toBeVisible();
  await expect(co.getByRole("button", { name: "送出記分" })).toHaveCount(0);
  await expect(
    co.getByRole("region", { name: "分數紀錄", exact: true }),
  ).toContainText("加分 +3");

  await page.reload();
  await page.getByRole("button", { name: "記分", exact: true }).click();
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[0].id));
  await page.getByLabel("加扣分種類").selectOption("negative");
  await page.getByLabel("原因模板").selectOption("other");
  await page.getByLabel("分數", { exact: true }).fill("0");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("扣分 0");
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  const history = page.getByRole("region", { name: "分數紀錄", exact: true });
  await expect(history).toContainText("扣分 0");
  await expect(history).toContainText("待補原因");
  await expect(page.getByLabel("記分學生", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "← 返回記分" }).click();
  await page.getByLabel("加扣分種類").selectOption("positive");
  await page.getByLabel("分數", { exact: true }).fill("0");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("加分 0");

  await page.getByLabel("加扣分種類").selectOption("negative");
  await page.getByLabel("分數", { exact: true }).fill("-5");
  await page.getByLabel("補充原因（選填）").fill("提醒後仍干擾討論");
  // The server commits, but the browser loses the response. Retrying must reuse the operation.
  await page.route(
    `**/api${base}scores/`,
    async (route) => {
      if (route.request().method() === "POST") {
        const response = await route.fetch();
        expect(response.status()).toBe(201);
        await route.abort("failed");
      } else await route.continue();
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  // Complete a different operation before retrying the unconfirmed one.
  await page.getByLabel("分數", { exact: true }).fill("-1");
  await page.getByLabel("補充原因（選填）").fill("另一筆課堂提醒");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("扣分 -1");
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  await expect(history).toContainText("共 5 筆");
  await expect(history).toContainText("加分 0");
  await page.getByRole("button", { name: "← 返回記分" }).click();
  await page.getByLabel("分數", { exact: true }).fill("-5");
  await page.getByLabel("補充原因（選填）").fill("提醒後仍干擾討論");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("扣分 -5");
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  await expect(history).toContainText("共 5 筆");
  await page.getByLabel("查看紀錄").selectOption(String(roster[0].id));
  await expect(history.locator(".score-total")).toHaveText("累積分數 -3");
  await page.screenshot({ path: ".local/scores-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".local/scores-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  await page.getByRole("button", { name: "← 返回記分" }).click();
  await page.getByLabel("補充原因（選填）").fill("尚未送出的草稿");
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  await expect(history.locator(".score-total")).toHaveText("累積分數 -3");
  await page.getByRole("button", { name: "← 返回記分" }).click();
  await expect(page.getByLabel("補充原因（選填）")).toHaveValue(
    "尚未送出的草稿",
  );
  await expect(page.getByLabel("記分學生", { exact: true })).toHaveValue(
    String(roster[0].id),
  );
  await expect(history).toHaveCount(0);
  await expect(page.getByLabel("查看紀錄")).toHaveCount(0);
  await page.screenshot({
    path: ".local/score-entry-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: ".local/score-entry-desktop.png",
    fullPage: true,
  });
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[1].id));
  await page.getByLabel("加扣分種類").selectOption("positive");
  await page.getByLabel("分數", { exact: true }).fill("9");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("小美");
  const studentContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const student = await studentContext.newPage();
  await student.goto(`/#student-login?class=${cohort.student_login_code}`);
  await student.getByLabel("學號", { exact: true }).fill("001");
  await student.getByLabel("密碼", { exact: true }).fill("001");
  await student.getByRole("button", { name: "學生登入", exact: true }).click();
  await student
    .getByLabel("新密碼", { exact: true })
    .fill("Student!Scoring2026");
  await student.getByLabel("確認新密碼").fill("Student!Scoring2026");
  await student.getByRole("button", { name: "儲存密碼並進入班級" }).click();
  const own = student.getByRole("region", { name: "我的分數", exact: true });
  await expect(own.locator(".score-total")).toHaveText("累積分數 -3");
  await expect(own.locator(".score-record")).toHaveCount(5);
  await expect(own).toContainText("共同教師陳");
  await expect(own).toContainText("待補原因");
  await expect(own).not.toContainText("小美");
  await expect(own).not.toContainText("加分 +9");
  await student.screenshot({
    path: ".local/student-scores-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await post(page, base + `teachers/${application.id}/`, {
    action: "remove",
    revision: 2,
  });
  await co.getByRole("button", { name: "重新整理紀錄" }).click();
  await expect(co.getByRole("alert")).toBeVisible();
  await expect(
    co.getByRole("region", { name: "分數紀錄", exact: true }),
  ).toHaveCount(0);
  await co.getByRole("button", { name: "← 返回記分" }).click();
  await expect(co.getByRole("alert")).toBeVisible();
  await expect(co.getByRole("button", { name: "送出記分" })).toHaveCount(0);
  await coContext.close();
  await studentContext.close();
});
