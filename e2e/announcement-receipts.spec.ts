import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";

test("students explicitly confirm the viewed version and homeroom tracks current readers", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
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
  await page.getByRole("button", { name: "班級公告", exact: true }).click();
  const teacherCard = page.locator(".announcement-card").first();
  await teacherCard.getByRole("button", { name: "已讀／未讀名單" }).click();
  await expect(teacherCard).toContainText("已讀 0 人 · 未讀 3 人");
  const context = await browser.newContext();
  const student = await context.newPage();
  await student.goto("/#student-login");
  await post(student, "/student/login/", {
    class_code: demo.student.class_code,
    student_number: "001",
    password: "001",
  });
  await post(student, "/student/change-password/", {
    password: "Receipt!Student2026",
  });
  await student.reload();
  const card = student.locator(".announcement-card").first();
  await expect(card).toContainText("尚未確認已讀");
  await card.getByRole("button", { name: /閱讀公告：/ }).click();
  await expect(card).toContainText("尚未確認已讀");
  // The server commits but the response is lost. Retrying must preserve one receipt.
  await student.route(
    "**/api/student/announcements/*/read/",
    async (route) => {
      await route.fetch();
      await route.abort("failed");
    },
    { times: 1 },
  );
  await card.getByRole("button", { name: "確認已讀", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  await card.getByRole("button", { name: "確認已讀", exact: true }).click();
  await expect(card.getByText(/已確認已讀 ·/)).toBeVisible();
  await teacherCard.getByRole("button", { name: "更新已讀名單" }).click();
  await expect(teacherCard).toContainText("已讀 1 人 · 未讀 2 人");
  await teacherCard.getByLabel("已讀狀態").selectOption("read");
  await expect(
    teacherCard.getByRole("list", { name: "公告閱讀名單" }),
  ).toContainText("展示小晴");
  await page.screenshot({
    path: ".local/v2-07-readers-desktop.png",
    fullPage: true,
  });
  const base = `/classes/${demo.cohort.id}/announcements/`;
  let item = (await (await page.request.get(`/api${base}`)).json()).results[0];
  item = await post(page, `${base}${item.id}/`, {
    action: "pin",
    revision: item.revision,
    request_id: randomUUID(),
    is_pinned: !item.is_pinned,
  });
  await student
    .getByRole("button", { name: "重新載入公告", exact: true })
    .click();
  await expect(card.getByText(/已確認已讀 ·/)).toBeVisible();
  item = await post(page, `${base}${item.id}/`, {
    action: "edit",
    revision: item.revision,
    request_id: randomUUID(),
    title: "公告第二版",
    body: item.body,
  });
  await student
    .getByRole("button", { name: "重新載入公告", exact: true })
    .click();
  await expect(card).toContainText("尚未確認已讀");
  // Student still sees version 2 when version 3 is published.
  await post(page, `${base}${item.id}/`, {
    action: "edit",
    revision: item.revision,
    request_id: randomUUID(),
    title: "公告第三版",
    body: item.body,
  });
  await card.getByRole("button", { name: "確認已讀", exact: true }).click();
  await expect(card.getByRole("alert")).toContainText("公告內容已更新");
  await expect(
    card.getByRole("button", { name: "確認已讀", exact: true }),
  ).toBeDisabled();
  await card.getByRole("button", { name: "載入最新公告" }).click();
  await expect(card).toContainText("公告第三版");
  await student.setViewportSize({ width: 320, height: 740 });
  await student.screenshot({
    path: ".local/v2-07-student-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await card.getByRole("button", { name: "確認已讀", exact: true }).click();
  await expect(card.getByText(/已確認已讀 ·/)).toBeVisible();
  await page.getByRole("button", { name: "重新載入公告", exact: true }).click();
  await teacherCard.getByRole("button", { name: "已讀／未讀名單" }).click();
  await expect(teacherCard).toContainText("已讀 1 人 · 未讀 2 人");
  await page.setViewportSize({ width: 320, height: 740 });
  await page.screenshot({
    path: ".local/v2-07-readers-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.close();
});
