import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";

test("notification bell opens the target and viewing never confirms announcement reading", async ({
  page,
  browser,
}) => {
  const demo = JSON.parse(
    execFileSync(
      resolve(".venv/Scripts/python.exe"),
      ["backend/manage.py", "create_demo"],
      {
        encoding: "utf8",
        windowsHide: true,
        env: { ...process.env, CM_DEBUG: "1", PYTHONIOENCODING: "utf-8" },
      },
    ),
  );
  async function post(target: Page, path: string, data: unknown) {
    const { csrfToken } = await (await target.request.get("/api/csrf/")).json();
    const response = await target.request.post(`/api${path}`, {
      headers: { "X-CSRFToken": csrfToken },
      data,
    });
    expect(response.ok()).toBe(true);
    return response.json();
  }
  await page.goto("/#login");
  await post(page, "/auth/login/", demo.teachers.homeroom);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "通知，0 則未查看", exact: true }),
  ).toBeVisible();
  const context = await browser.newContext();
  const student = await context.newPage();
  await student.goto("/#student-login");
  await post(student, "/student/login/", {
    class_code: demo.student.class_code,
    student_number: "001",
    password: "001",
  });
  await post(student, "/student/change-password/", {
    password: "Notification!Student2026",
  });
  await student.reload();
  await expect(
    student.getByRole("button", { name: "通知，0 則未查看", exact: true }),
  ).toBeVisible();
  const base = `/classes/${demo.cohort.id}/announcements/`;
  const body = {
    type: "doc",
    content: [
      { type: "paragraph", content: [{ type: "text", text: "明天校外教學" }] },
    ],
  };
  const item = await post(page, base, {
    title: "通知目標公告",
    body,
    request_id: randomUUID(),
  });
  await student
    .getByRole("button", { name: "通知，0 則未查看", exact: true })
    .click();
  const dialog = student.getByRole("dialog", { name: "通知中心" });
  await expect(dialog).toContainText("1 則未查看");
  await student.route(
    "**/api/notifications/*/open/",
    async (route) => {
      await route.fetch();
      await route.abort("failed");
    },
    { times: 1 },
  );
  await dialog.getByRole("button", { name: "新公告：通知目標公告" }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await dialog.getByRole("button", { name: "新公告：通知目標公告" }).click();
  await expect(dialog).toContainText("尚未確認已讀");
  await expect(
    dialog.getByRole("heading", { name: "通知目標公告", exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "← 返回公告清單", exact: true })
    .click();
  await expect(dialog.locator(".announcement-card")).toHaveCount(2);
  const announcementButton = dialog.getByRole("button", {
    name: "閱讀公告：通知目標公告",
    exact: true,
  });
  await announcementButton.click();
  await dialog
    .getByRole("button", { name: "← 返回公告清單", exact: true })
    .click();
  await expect(announcementButton).toBeFocused();
  await dialog.getByRole("button", { name: "關閉通知" }).click();
  await expect(
    student.getByRole("button", { name: "通知，0 則未查看", exact: true }),
  ).toBeVisible();
  await post(page, base + `${item.id}/`, {
    action: "edit",
    revision: item.revision,
    title: "更新後的通知目標公告",
    body,
    request_id: randomUUID(),
  });
  await student.getByRole("button", { name: /通知，/ }).click();
  await expect(dialog).toContainText("1 則未查看");
  await dialog.getByRole("button", { name: "全部已查看", exact: true }).click();
  await expect(dialog).toContainText("0 則未查看");
  await expect(dialog).toContainText("公告仍需手動確認已讀");
  await student.screenshot({
    path: ".local/v2-08-notifications-desktop.png",
    fullPage: true,
  });
  await student.setViewportSize({ width: 320, height: 740 });
  await student.screenshot({
    path: ".local/v2-08-notifications-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await dialog
    .getByRole("button", { name: "公告內容更新：更新後的通知目標公告" })
    .click();
  await expect(dialog).toContainText("尚未確認已讀");
  await context.close();
});

test("homeroom notifications open current applications and comments while co-teachers have no bell", async ({
  page,
  browser,
}) => {
  const demo = JSON.parse(
    execFileSync(
      resolve(".venv/Scripts/python.exe"),
      ["backend/manage.py", "create_demo"],
      {
        encoding: "utf8",
        windowsHide: true,
        env: { ...process.env, CM_DEBUG: "1", PYTHONIOENCODING: "utf-8" },
      },
    ),
  );
  async function post(target: Page, path: string, data: unknown) {
    const { csrfToken } = await (await target.request.get("/api/csrf/")).json();
    const response = await target.request.post(`/api${path}`, {
      headers: { "X-CSRFToken": csrfToken },
      data,
    });
    expect(response.ok()).toBe(true);
    return response.json();
  }
  await page.goto("/#login");
  await post(page, "/auth/login/", demo.teachers.homeroom);
  await page.reload();
  const context = await browser.newContext();
  const co = await context.newPage();
  await co.goto("/#login");
  await post(co, "/auth/login/", demo.teachers.coTeacher);
  await co.reload();
  await expect(
    co.getByRole("heading", { name: "我的班級", exact: true }),
  ).toBeVisible();
  await expect(co.getByRole("button", { name: /通知，/ })).toHaveCount(0);
  const base = `/classes/${demo.cohort.id}/`;
  const item = (
    await (await page.request.get(`/api${base}announcements/`)).json()
  ).results[0];
  await post(co, base + `announcements/${item.id}/comments/`, {
    request_id: randomUUID(),
    body: {
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "新的留言" }] },
      ],
    },
  });
  await page.getByRole("button", { name: /通知，/ }).click();
  const dialog = page.getByRole("dialog", { name: "通知中心" });
  await expect(dialog).toContainText("1 則未查看");
  await dialog
    .getByRole("button", { name: `公告新留言：${item.title}` })
    .click();
  await expect(
    dialog.getByRole("heading", { name: item.title, exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: /^留言（/ }).click();
  await expect(dialog).toContainText("新的留言");
  await dialog.getByRole("button", { name: "關閉通知" }).click();
  const teachers = await (
    await page.request.get(`/api${base}teachers/`)
  ).json();
  const member = teachers.members.find(
    (m: { status: string }) => m.status === "approved",
  );
  await post(page, base + `teachers/${member.id}/`, {
    action: "remove",
    revision: member.revision,
  });
  await post(co, "/teacher-applications/", {
    application_code: teachers.application_code,
  });
  await page.getByRole("button", { name: /通知，/ }).click();
  await dialog.getByRole("button", { name: "教師申請：教師加入申請" }).click();
  await expect(dialog.getByRole("heading", { name: /教師管理/ })).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "批准", exact: true }).first(),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/v2-08-teacher-mobile.png",
    fullPage: false,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.close();
});
