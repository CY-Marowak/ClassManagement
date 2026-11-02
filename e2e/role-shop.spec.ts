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

test("student previews buys retries and switches roles without changing score or growth", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  const email = `shop-${Date.now()}@example.com`;
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
    items: [{ record_id: record.id, revision: 1, points: 25 }],
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
  await student
    .getByRole("button", { name: "我的角色收藏", exact: true })
    .click();
  await expect(student.getByText("可用點數 25", { exact: true })).toBeVisible();
  const before = await (
    await student.request.get("/api/student/roles/")
  ).json();
  const item = before.catalog.find(
    (r: { id: string }) => !before.owned.includes(r.id),
  );
  await student
    .getByRole("button", { name: `預覽${item.name}`, exact: true })
    .click();
  const preview = student.getByRole("region", { name: "確認購買角色" });
  await expect(preview).toBeFocused();
  await expect(preview).toContainText("價格 20 點");
  await expect(preview).toContainText("預計餘額 5 點");
  await expect(preview).toContainText(item.name);
  await student.screenshot({
    path: ".local/v2-03-shop-desktop.png",
    fullPage: true,
  });
  await student.setViewportSize({ width: 390, height: 844 });
  await student.screenshot({
    path: ".local/v2-03-shop-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await preview.getByRole("button", { name: "取消" }).click();
  await expect(
    student.getByRole("button", { name: `預覽${item.name}`, exact: true }),
  ).toBeFocused();
  expect(
    (await (await student.request.get("/api/student/roles/")).json()).owned,
  ).toHaveLength(1);
  await student
    .getByRole("button", { name: `預覽${item.name}`, exact: true })
    .click();
  await student.route(
    "**/api/student/roles/purchases/",
    async (route) => {
      const result = await route.fetch();
      expect(result.status()).toBe(201);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await preview.getByRole("button", { name: "確認購買 · 20 點" }).click();
  await expect(student.getByRole("alert")).toBeVisible();
  await student.reload();
  await student
    .getByRole("button", { name: "我的角色收藏", exact: true })
    .click();
  await student
    .getByRole("button", { name: "重試這次購買", exact: true })
    .click();
  await expect(
    student.getByRole("status").filter({ hasText: "已加入收藏" }),
  ).toBeVisible();
  await expect(student.getByText("可用點數 5", { exact: true })).toBeVisible();
  const collection = await (
    await student.request.get("/api/student/roles/")
  ).json();
  expect(collection.selected).toBe(before.selected);
  expect(collection.owned).toHaveLength(2);
  await expect(
    student.getByRole("button", { name: `預覽${item.name}`, exact: true }),
  ).toHaveCount(0);
  const next = collection.catalog.find(
    (r: { id: string }) => !collection.owned.includes(r.id),
  );
  await student
    .getByRole("button", { name: `預覽${next.name}`, exact: true })
    .click();
  await expect(preview).toContainText("點數不足");
  await expect(
    preview.getByRole("button", { name: "確認購買 · 20 點" }),
  ).toBeDisabled();
  await preview.getByRole("button", { name: "取消" }).click();
  await student
    .getByRole("button", { name: `換上${item.name}`, exact: true })
    .click();
  await expect(student.getByLabel("目前使用角色")).toContainText(item.name);
  await student.getByRole("button", { name: "返回我的頁面" }).click();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toContainText("可用點數 5");
  await expect(student.locator(".score-total")).toHaveText("累積分數 3");
  await student.getByRole("button", { name: "餵食班級吉祥物" }).click();
  await expect(
    student.getByText("累積總餵食量 0 exp", { exact: true }),
  ).toBeVisible();
  await expect(
    student.getByText("今日還可餵 5 點", { exact: true }),
  ).toBeVisible();
  await expect(
    student
      .locator(".point-transaction")
      .filter({ hasText: `購買角色 · ${item.name}` }),
  ).toContainText("-20 點");
  await expect(student.locator(".point-transaction")).toHaveCount(2);
  const secondRecord = await post(page, base + "scores/", {
    student_id: students[0].id,
    kind: "positive",
    score: 0,
    template: "helping",
    note: "第二次收藏獎勵",
    request_id: crypto.randomUUID(),
  });
  await post(page, base + "point-awards/", {
    request_id: crypto.randomUUID(),
    items: [{ record_id: secondRecord.id, revision: 1, points: 20 }],
  });
  await student.getByRole("button", { name: "返回我的頁面" }).click();
  await student
    .getByRole("button", { name: "我的角色收藏", exact: true })
    .click();
  await expect(student.getByText("可用點數 25", { exact: true })).toBeVisible();
  await student
    .getByRole("button", { name: `預覽${next.name}`, exact: true })
    .click();
  await student.route(
    "**/api/student/roles/",
    (route) => route.abort("failed"),
    { times: 1 },
  );
  await preview.getByRole("button", { name: "確認購買 · 20 點" }).click();
  await expect(student.getByRole("alert")).toBeVisible();
  await student.getByRole("button", { name: "返回我的頁面" }).click();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toContainText("可用點數 5");
  const thirdRecord = await post(page, base + "scores/", {
    student_id: students[0].id,
    kind: "positive",
    score: 0,
    template: "helping",
    note: "跨分頁收藏獎勵",
    request_id: crypto.randomUUID(),
  });
  await post(page, base + "point-awards/", {
    request_id: crypto.randomUUID(),
    items: [{ record_id: thirdRecord.id, revision: 1, points: 20 }],
  });
  await student
    .getByRole("button", { name: "我的角色收藏", exact: true })
    .click();
  await expect(student.getByText("可用點數 25", { exact: true })).toBeVisible();
  const current = await (
    await student.request.get("/api/student/roles/")
  ).json();
  const third = current.catalog.find(
    (r: { id: string }) => !current.owned.includes(r.id),
  );
  await student
    .getByRole("button", { name: `預覽${third.name}`, exact: true })
    .click();
  // A second tab buys while this tab is still displaying its old preview.
  const otherTab = await context.newPage();
  await otherTab.goto("/#student");
  await post(otherTab, "/student/roles/purchases/", {
    role: third.id,
    request_id: crypto.randomUUID(),
  });
  await preview.getByRole("button", { name: "確認購買 · 20 點" }).click();
  await expect(student.getByRole("alert")).toContainText("已擁有這個角色");
  await expect(student.getByText("可用點數 5", { exact: true })).toBeVisible();
  await expect(
    student.getByRole("heading", { name: "已擁有 · 4 種" }),
  ).toBeVisible();
  await expect(preview).toHaveCount(0);
  await context.close();
});
