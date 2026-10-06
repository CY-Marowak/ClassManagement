import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.use({ actionTimeout: 10000 });
test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    Object.defineProperty(crypto, "randomUUID", { value: undefined });
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

async function teacher(page: Page, name: string) {
  const email = `${name}-${Date.now()}@example.com`;
  const password = "Comments!Teacher2026";
  await page.goto("/#login");
  await post(page, "/auth/register/", { email, password, display_name: name });
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    { encoding: "utf8", windowsHide: true },
  ).trim();
  await post(page, "/auth/verify/", {
    token: new URLSearchParams(new URL(link).hash.split("?")[1]).get("token"),
  });
  await post(page, "/auth/login/", { email, password });
}

test("co-teacher comments, student reads and homeroom moderates without authoring", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await teacher(owner, "comment-owner");
  const cohort = await post(owner, "/classes/", {
    name: "留言班",
    entry_year: 2026,
    current_grade: 1,
  });
  const base = `/classes/${cohort.id}/`;
  await post(owner, base + "students/", { text: "1\t小明\t001" });
  const body = {
    type: "doc",
    content: [
      { type: "paragraph", content: [{ type: "text", text: "明日校外教學" }] },
    ],
  };
  const announcement = await post(owner, base + "announcements/", {
    title: "出發提醒",
    body,
    request_id: crypto.randomUUID(),
  });
  await post(owner, base + "announcements/", {
    title: "另一篇閱讀測試",
    body,
    request_id: crypto.randomUUID(),
  });
  const { application_code } = await (
    await owner.request.get(`/api${base}teachers/`)
  ).json();
  await teacher(page, "comment-colleague");
  await post(page, "/teacher-applications/", { application_code });
  const { members } = await (
    await owner.request.get(`/api${base}teachers/`)
  ).json();
  await post(owner, base + `teachers/${members[0].id}/`, {
    action: "approve",
    revision: members[0].revision,
  });
  await page.reload();
  await page.getByRole("button", { name: "班級公告", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "留言內文" })).toHaveCount(0);
  await page
    .locator(".announcement-card")
    .filter({ hasText: "出發提醒" })
    .getByRole("button", { name: "留言（0）", exact: true })
    .click();
  const editor = page.getByRole("textbox", { name: "留言內文" });
  await editor.fill("請帶雨衣");
  await editor.press("ControlOrMeta+a");
  await page.getByRole("button", { name: "斜體", exact: true }).click();
  await page.getByLabel("文字顏色").selectOption("#175cd3");
  const path = `/api${base}announcements/${announcement.id}/comments/`;
  await page.route(
    `**${path}`,
    async (route) => {
      const result = await route.fetch();
      expect(result.status()).toBe(201);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "發布留言", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(editor).toHaveAttribute("contenteditable", "false");
  await page
    .getByRole("button", { name: "閱讀公告：另一篇閱讀測試", exact: true })
    .click();
  await expect(page.locator(".announcement-card:visible")).toHaveCount(1);
  await page
    .getByRole("button", { name: "← 返回公告清單", exact: true })
    .click();
  await expect(editor).toHaveText("請帶雨衣");
  await page.getByRole("button", { name: "重試這次留言操作" }).click();
  await expect(page.locator(".comment-card")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "留言（1）", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".comment-card em")).toHaveText("請帶雨衣");
  await page
    .locator(".comment-card")
    .getByRole("button", { name: "編輯留言", exact: true })
    .click();
  await editor.fill("請帶輕便雨衣");
  await page.getByRole("button", { name: "儲存留言", exact: true }).click();
  await expect(page.locator(".comment-card")).toContainText("已編輯");
  await expect(page.locator(".comment-card")).toContainText("請帶輕便雨衣");
  await page.screenshot({
    path: ".local/11-comments-desktop.png",
    fullPage: true,
  });
  const studentContext = await browser.newContext();
  const student = await studentContext.newPage();
  await student.goto("/#student-login");
  await post(student, "/student/login/", {
    class_code: cohort.student_login_code,
    student_number: "001",
    password: "001",
  });
  await post(student, "/student/change-password/", {
    password: "Student!Comments2026",
  });
  await student.reload();
  await student.getByRole("button", { name: "留言（1）", exact: true }).click();
  await expect(student.locator(".comment-card")).toContainText("請帶輕便雨衣");
  await expect(student.getByRole("textbox", { name: "留言內文" })).toHaveCount(
    0,
  );
  await expect(student.getByRole("button", { name: "刪除留言" })).toHaveCount(
    0,
  );
  await student.setViewportSize({ width: 390, height: 844 });
  await student.screenshot({
    path: ".local/11-comments-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await owner.reload();
  await owner.getByRole("button", { name: "班級公告", exact: true }).click();
  await owner.getByRole("button", { name: "留言（1）", exact: true }).click();
  await expect(owner.getByRole("textbox", { name: "留言內文" })).toHaveCount(0);
  await expect(owner.getByRole("button", { name: "編輯留言" })).toHaveCount(0);
  await owner.getByRole("button", { name: "刪除留言", exact: true }).click();
  let releaseRefresh!: () => void;
  const refreshGate = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  await owner.route(
    `**${path}?page=1`,
    async (route) => {
      const response = await route.fetch();
      await refreshGate;
      await route.fulfill({ response });
    },
    { times: 1 },
  );
  await owner.getByRole("button", { name: "更新留言", exact: true }).click();
  try {
    await expect(
      owner.getByRole("button", { name: "確認刪除留言", exact: true }),
    ).toBeDisabled();
  } finally {
    releaseRefresh();
  }
  await expect(owner.getByText("正在載入留言…", { exact: true })).toHaveCount(
    0,
  );
  await owner
    .getByRole("button", { name: "確認刪除留言", exact: true })
    .click();
  await expect(owner.locator(".comment-card")).toHaveCount(0);
  await expect(
    owner
      .locator(".announcement-card")
      .filter({ hasText: "出發提醒" })
      .getByRole("button", { name: "留言（0）", exact: true }),
  ).toBeVisible();
  await student.getByRole("button", { name: "更新留言", exact: true }).click();
  await expect(student.locator(".comment-card")).toHaveCount(0);
  // More than one page: old-to-new ordering, and new posts land on the last page.
  for (let i = 1; i <= 21; i++) {
    await post(page, path.slice(4), {
      request_id: crypto.randomUUID(),
      body: {
        type: "doc",
        content: [
          { type: "paragraph", content: [{ type: "text", text: `補充 ${i}` }] },
        ],
      },
    });
  }
  await page.getByRole("button", { name: "更新留言", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(20);
  await expect(page.locator(".comment-card").first()).toContainText("補充 1");
  await page.getByRole("button", { name: "下一頁留言", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(1);
  await expect(page.locator(".comment-card")).toContainText("補充 21");
  await editor.fill("最後一則");
  await page.getByRole("button", { name: "發布留言", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(2);
  const last = page.locator(".comment-card").last();
  await last.getByRole("button", { name: "編輯留言", exact: true }).click();
  const current = (
    await (await page.request.get(path + "?page=2")).json()
  ).results.at(-1);
  await post(page, path.slice(4) + `${current.id}/`, {
    action: "edit",
    revision: current.revision,
    request_id: crypto.randomUUID(),
    body,
  });
  await editor.fill("舊視窗不能覆蓋");
  await page.getByRole("button", { name: "儲存留言", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("留言已變更");
  await page.getByRole("button", { name: "捨棄舊操作並重新載入留言" }).click();
  await page.getByRole("button", { name: "下一頁留言", exact: true }).click();
  await expect(last).toContainText("明日校外教學");
  await last.getByRole("button", { name: "刪除留言", exact: true }).click();
  await page.route(
    `**${path}?page=1`,
    (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "暫時讀取失敗" }),
      }),
    { times: 1 },
  );
  await page.getByRole("button", { name: "確認刪除留言", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("留言操作已完成");
  await expect(
    page.getByRole("button", { name: "確認刪除留言", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "更新留言", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(1);
  await page.getByRole("button", { name: "編輯留言", exact: true }).click();
  await editor.fill("尚未送出的草稿");
  await page.route(`**${path}?page=2`, (route) => route.abort("failed"), {
    times: 1,
  });
  await page.getByRole("button", { name: "更新留言", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(editor).toContainText("尚未送出的草稿");
  const latestMembers = await (
    await owner.request.get(`/api${base}teachers/`)
  ).json();
  await post(owner, base + `teachers/${members[0].id}/`, {
    action: "remove",
    revision: latestMembers.members[0].revision,
  });
  await page.getByRole("button", { name: "更新留言", exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.locator(".comment-card")).toHaveCount(0);
  await owner.getByRole("button", { name: "更新留言", exact: true }).click();
  await owner
    .getByRole("button", { name: "刪除留言", exact: true })
    .first()
    .click();
  await post(owner, base + `announcements/${announcement.id}/`, {
    action: "delete",
    revision: announcement.revision,
    request_id: crypto.randomUUID(),
  });
  await owner.getByRole("button", { name: "更新留言", exact: true }).click();
  await expect(
    owner.getByRole("alertdialog", { name: "刪除留言確認" }),
  ).toHaveCount(0);
  await expect(owner.locator(".comment-card")).toHaveCount(0);
  await studentContext.close();
  await ownerContext.close();
});
