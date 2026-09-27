import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.use({ actionTimeout: 10000 });

test("teachers award own sources once, recover stale selections, and keep points after deletion", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  const suffix = Date.now();
  await teacher(page, `award-${suffix}@example.com`, "發點導師");
  const cohort = await post(page, "/classes/", {
    name: "獎勵班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(page, base + "students/", { text: "1\t小明\t001\n2\t小美\t002" });
  const students = await (
    await page.request.get(`/api${base}students/`)
  ).json();
  const records = (
    await post(page, base + "score-batches/", {
      student_ids: students.map((s: { id: number }) => s.id),
      kind: "positive",
      score: 0,
      template: "participation",
      note: "合作練習",
      request_id: crypto.randomUUID(),
    })
  ).results;
  const coContext = await browser.newContext();
  const co = await coContext.newPage();
  await teacher(co, `award-co-${suffix}@example.com`, "共同發點教師");
  const code = (await (await page.request.get(`/api${base}teachers/`)).json())
    .application_code;
  const member = await post(co, "/teacher-applications/", {
    application_code: code,
  });
  await post(page, base + `teachers/${member.id}/`, {
    action: "approve",
    revision: 1,
  });
  await post(co, base + "scores/", {
    student_id: students[0].id,
    kind: "positive",
    score: 1,
    template: "helping",
    note: "共同教師獎勵",
    request_id: crypto.randomUUID(),
  });
  await page.reload();
  await page.getByRole("button", { name: "發點數", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "發點數", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("共同教師獎勵", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("checkbox")).toHaveCount(2);
  await page.getByRole("button", { name: "全選本頁" }).click();
  await page.getByLabel("小明的發放點數").fill("3");
  await page.screenshot({
    path: ".local/08-pending-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/08-pending-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  // A source changes in another tab after selection. Nothing may be awarded.
  const preview = await (
    await page.request.get(`/api${base}scores/${records[1].id}/edit-preview/`)
  ).json();
  await post(page, base + "score-changes/", {
    action: "edit",
    preview_token: preview.token,
    request_id: crypto.randomUUID(),
    kind: "positive",
    score: 2,
    template: "helping",
    note: "最新原因",
  });
  await page.getByRole("button", { name: "發放所選點數" }).click();
  await expect(page.getByRole("alert")).toContainText("小美");
  await expect(page.getByRole("alert")).toContainText("整批未儲存");
  await page.getByRole("button", { name: "重新整理發點名單" }).click();
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(0);
  await page.getByRole("button", { name: "全選本頁" }).click();
  await page.getByLabel("小明的發放點數").fill("3");
  await page.route(
    `**/api${base}point-awards/`,
    async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "發放所選點數" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("小明的發放點數")).toHaveValue("3");
  await page.getByRole("button", { name: "發放所選點數" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText(
    "已發放 4 點，共 2 筆",
  );
  await expect(
    page.getByText("本週本人已發放 4 點 · 2 筆", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("發點狀態").selectOption("awarded");
  await expect(page.getByText("已發放 3 點", { exact: true })).toBeVisible();
  await page.screenshot({
    path: ".local/08-awards-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/08-awards-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "← 返回我的班級" }).click();
  await page.getByRole("button", { name: "記分", exact: true }).click();
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  const row = page.locator(".score-record").filter({ hasText: "合作練習" });
  await expect(row).toContainText("已發放 3 點");
  await row.getByRole("button", { name: "刪除紀錄" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "已發放 3 點，刪除後不回收",
  );
  await page.getByRole("button", { name: "確認刪除紀錄" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "← 返回我的班級" }).click();
  await page.getByRole("button", { name: "發點數", exact: true }).click();
  await page.getByLabel("發點狀態").selectOption("awarded");
  const awarded = page.getByRole("region", { name: "1 號 · 小明" });
  await expect(awarded).toContainText("已發放 3 點");
  await expect(awarded).toContainText("來源已刪除");
  await co.reload();
  await co.getByRole("button", { name: "發點數", exact: true }).click();
  await expect(co.getByRole("checkbox")).toHaveCount(1);
  await expect(
    co.getByText("本週本人已發放 0 點 · 0 筆", { exact: true }),
  ).toBeVisible();
  await co.getByRole("button", { name: "全選本頁" }).click();
  await co.getByRole("button", { name: "發放所選點數" }).click();
  await expect(co.locator('.notice[role="status"]')).toContainText(
    "已發放 1 點，共 1 筆",
  );
  await post(page, base + `teachers/${member.id}/`, {
    action: "remove",
    revision: 2,
  });
  await co.getByRole("button", { name: "重新整理發點名單" }).click();
  await expect(co.getByRole("alert")).toBeVisible();
  await expect(co.getByRole("checkbox")).toHaveCount(0);
  await coContext.close();
});

test("score edits preserve exceptions, delete safely, and show audit differences", async ({
  page,
}) => {
  test.setTimeout(90000);
  await teacher(page, `edit-${Date.now()}@example.com`, "修正導師");
  const cohort = await post(page, "/classes/", {
    name: "修正班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(page, base + "students/", {
    text: "1\t小明\t001\n2\t小美\t002\n3\t小華\t003",
  });
  const students = await (
    await page.request.get(`/api${base}students/`)
  ).json();
  const batch = await post(page, base + "score-batches/", {
    student_ids: students.map((s: { id: number }) => s.id),
    kind: "positive",
    score: 2,
    template: "participation",
    note: "全班合作",
    request_id: crypto.randomUUID(),
  });
  await page.reload();
  await page.getByRole("button", { name: "記分", exact: true }).click();
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  const record = (name: string) =>
    page.locator(".score-record").filter({ hasText: name });
  const dialog = page.getByRole("dialog");
  await record("小明")
    .getByRole("button", { name: "修改這筆", exact: true })
    .click();
  await expect(
    dialog.getByRole("heading", { name: "本次修改 1 筆" }),
  ).toBeVisible();
  await dialog.getByLabel("分數", { exact: true }).fill("1");
  await page.route(
    `**/api${base}score-changes/`,
    async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await dialog.getByRole("button", { name: "確認儲存修改" }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  // Editing the draft and returning must keep the original request identity.
  await dialog.getByLabel("分數", { exact: true }).fill("8");
  await dialog.getByLabel("分數", { exact: true }).fill("1");
  await dialog.getByRole("button", { name: "確認儲存修改" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(record("小明")).toContainText("加分 +1");
  await expect(
    record("小明").getByText("已修改", { exact: true }),
  ).toBeVisible();
  await record("小美")
    .getByRole("button", { name: "刪除紀錄", exact: true })
    .click();
  await expect(dialog).toContainText("已發放點數不回收");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(record("小美")).toHaveCount(1);
  await record("小美")
    .getByRole("button", { name: "刪除紀錄", exact: true })
    .click();
  await expect(
    dialog.getByRole("heading", { name: "本次刪除 1 筆" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "確認刪除紀錄" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(record("小美")).toHaveCount(0);
  await record("小華")
    .getByRole("button", { name: "修改同批", exact: true })
    .click();
  await expect(
    dialog.getByRole("heading", { name: "本次修改 1 筆" }),
  ).toBeVisible();
  await expect(dialog).toContainText("略過 2 筆");
  await expect(dialog).toContainText("小明：已個別修改");
  await expect(dialog).toContainText("小美：已刪除");
  await dialog.getByLabel("分數", { exact: true }).fill("3");
  await page.screenshot({ path: ".local/07-edit-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".local/07-edit-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // Simulate another tab saving after this preview. The stale confirmation must fail.
  const anchor = batch.results.find(
    (r: { student_name: string }) => r.student_name === "小華",
  );
  const preview = await (
    await page.request.get(
      `/api${base}scores/${anchor.id}/edit-preview/?scope=batch`,
    )
  ).json();
  await post(page, base + "score-changes/", {
    action: "edit",
    preview_token: preview.token,
    request_id: crypto.randomUUID(),
    kind: "positive",
    score: 4,
    template: "helping",
    note: "另頁已修正",
  });
  await dialog.getByRole("button", { name: "確認儲存修改" }).click();
  await expect(dialog.getByRole("alert")).toContainText("整批未儲存");
  await dialog.getByRole("button", { name: "重新載入預覽" }).click();
  await expect(dialog.getByLabel("分數", { exact: true })).toHaveValue("4");
  await dialog.getByLabel("分數", { exact: true }).fill("3");
  await dialog.getByRole("button", { name: "確認儲存修改" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(record("小華")).toContainText("加分 +3");
  await expect(record("小明")).toContainText("加分 +1");
  await page.getByRole("button", { name: "查看分數查核", exact: true }).click();
  const audit = page.getByRole("region", { name: "分數查核", exact: true });
  await expect(audit).toContainText("刪除記分");
  await expect(audit).toContainText("4 → 3");
  await expect(audit).toContainText("共 7 筆");
  await page.screenshot({ path: ".local/07-audit-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: ".local/07-audit-desktop.png",
    fullPage: true,
  });
});

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
  await expect(page.getByLabel("記分模式")).toHaveValue("batch");
  await expect(page.getByText("已選 2 位學生", { exact: true })).toBeVisible();
  await expect(page.getByLabel("原因模板")).toHaveValue("other");
  await expect(page.getByLabel("分數", { exact: true })).toHaveValue("2");
  await page.getByRole("button", { name: "送出批次記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText(
    "已記錄 2 位學生",
  );
  await expectInitialScoreForm(page);
  await page.getByLabel("記分模式").selectOption("batch");
  await expect(page.getByText("已選 0 位學生", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "送出批次記分" }),
  ).toBeDisabled();
  await page.getByLabel("記分模式").selectOption("single");
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
  await expectInitialScoreForm(page);
  await page.getByLabel("記分模式").selectOption("batch");
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

async function expectInitialScoreForm(page: Page) {
  await expect(page.getByLabel("記分模式")).toHaveValue("single");
  await expect(page.getByLabel("記分學生", { exact: true })).toHaveValue("");
  await expect(
    page.getByLabel("記分學生").locator("option:checked"),
  ).toHaveText("選擇學生（依座號）");
  await expect(page.getByLabel("加扣分種類")).toHaveValue("positive");
  await expect(page.getByLabel("分數", { exact: true })).toHaveValue("1");
  await expect(page.getByLabel("原因模板")).toHaveValue("participation");
  await expect(page.getByLabel("補充原因（選填）")).toHaveValue("");
  await expect(page.getByRole("button", { name: "送出記分" })).toBeDisabled();
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
  await expectInitialScoreForm(co);
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
  await expectInitialScoreForm(page);
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  const history = page.getByRole("region", { name: "分數紀錄", exact: true });
  await expect(history).toContainText("扣分 0");
  await expect(history).toContainText("待補原因");
  await expect(page.getByLabel("記分學生", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "← 返回記分" }).click();
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[0].id));
  await page.getByLabel("加扣分種類").selectOption("positive");
  await page.getByLabel("分數", { exact: true }).fill("0");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("加分 0");
  await expectInitialScoreForm(page);

  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[0].id));
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
  await expect(page.getByLabel("記分學生", { exact: true })).toHaveValue(
    String(roster[0].id),
  );
  await expect(page.getByLabel("加扣分種類")).toHaveValue("negative");
  await expect(page.getByLabel("分數", { exact: true })).toHaveValue("-5");
  await expect(page.getByLabel("原因模板")).toHaveValue("disruption");
  await expect(page.getByLabel("補充原因（選填）")).toHaveValue(
    "提醒後仍干擾討論",
  );
  // Complete a different operation before retrying the unconfirmed one.
  await page.getByLabel("分數", { exact: true }).fill("-1");
  await page.getByLabel("補充原因（選填）").fill("另一筆課堂提醒");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("扣分 -1");
  await page.getByRole("button", { name: "查看分數紀錄 →" }).click();
  await expect(history).toContainText("共 5 筆");
  await expect(history).toContainText("加分 0");
  await page.getByRole("button", { name: "← 返回記分" }).click();
  await expectInitialScoreForm(page);
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[0].id));
  await page.getByLabel("加扣分種類").selectOption("negative");
  await page.getByLabel("分數", { exact: true }).fill("-5");
  await page.getByLabel("補充原因（選填）").fill("提醒後仍干擾討論");
  await page.getByRole("button", { name: "送出記分" }).click();
  await expect(page.locator('.notice[role="status"]')).toContainText("扣分 -5");
  await expectInitialScoreForm(page);
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
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption(String(roster[0].id));
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
  await co.getByRole("button", { name: "重新整理紀錄", exact: true }).click();
  const coHistory = co.getByRole("region", { name: "分數紀錄", exact: true });
  await expect(coHistory.locator(".score-record")).toHaveCount(6);
  await expect(
    coHistory.getByRole("button", { name: "修改這筆", exact: true }),
  ).toHaveCount(1);
  await expect(
    coHistory.getByRole("button", { name: "刪除紀錄", exact: true }),
  ).toHaveCount(1);
  await expect(
    co.getByRole("button", { name: "查看分數查核", exact: true }),
  ).toHaveCount(0);
  await coHistory
    .getByRole("button", { name: "修改這筆", exact: true })
    .click();
  const coDialog = co.getByRole("dialog");
  await expect(
    coDialog.getByRole("heading", { name: "本次修改 1 筆" }),
  ).toBeVisible();
  await coDialog.getByLabel("補充原因（選填）").fill("補記分享過程");
  await coDialog.getByRole("button", { name: "確認儲存修改" }).click();
  await expect(coDialog).toHaveCount(0);
  await student.getByRole("button", { name: "更新分數紀錄" }).click();
  await expect(own.getByText("已修改", { exact: true })).toHaveCount(1);
  await expect(own).toContainText("補記分享過程");
  await expect(
    own.getByRole("button", { name: "修改這筆", exact: true }),
  ).toHaveCount(0);
  await coHistory
    .getByRole("button", { name: "刪除紀錄", exact: true })
    .click();
  await expect(
    coDialog.getByRole("heading", { name: "本次刪除 1 筆" }),
  ).toBeVisible();
  await coDialog.getByRole("button", { name: "確認刪除紀錄" }).click();
  await expect(coDialog).toHaveCount(0);
  await student.getByRole("button", { name: "更新分數紀錄" }).click();
  await expect(own.locator(".score-total")).toHaveText("累積分數 -6");
  await expect(own.locator(".score-record")).toHaveCount(4);
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
