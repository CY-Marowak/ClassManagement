import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("homeroom manually reminds unread students and student views without confirming", async ({
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
  await page.goto("/#login");
  const token = (await (await page.request.get("/api/csrf/")).json()).csrfToken;
  expect(
    (
      await page.request.post("/api/auth/login/", {
        headers: { "X-CSRFToken": token },
        data: demo.teachers.homeroom,
      })
    ).ok(),
  ).toBe(true);
  await page.reload();
  await page.getByRole("button", { name: "班級公告", exact: true }).click();
  await page
    .getByRole("button", { name: /閱讀公告：/ })
    .first()
    .click();
  await page
    .getByRole("button", { name: "已讀／未讀名單", exact: true })
    .click();
  const reminders = page.getByRole("region", {
    name: "手動未讀提醒",
    exact: true,
  });
  await expect(reminders).toBeVisible();
  await reminders.getByLabel("提醒對象").selectOption({ index: 1 });
  await page.route(
    "**/reminders/",
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fetch();
      await route.abort("failed");
    },
    { times: 1 },
  );
  await reminders
    .getByRole("button", { name: "發送提醒", exact: true })
    .click();
  await expect(reminders.getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "更新已讀名單" }),
  ).toBeDisabled();
  await reminders
    .getByRole("button", { name: "重試這次提醒", exact: true })
    .click();
  await expect(reminders).toContainText("已發送 1 人");
  await reminders.getByLabel("提醒對象").selectOption("all");
  await reminders
    .getByRole("button", { name: "發送提醒", exact: true })
    .click();
  await expect(reminders).toContainText("今日已提醒 1 人");
  await reminders
    .getByRole("button", { name: "查看提醒紀錄", exact: true })
    .click();
  await expect(
    reminders.getByRole("list", { name: "已發提醒紀錄" }).getByRole("listitem"),
  ).toHaveCount(3);
  const context = await browser.newContext();
  const student = await context.newPage();
  await student.goto("/#student-login");
  async function post(path: string, data: unknown) {
    const csrf = (await (await student.request.get("/api/csrf/")).json())
      .csrfToken;
    expect(
      (
        await student.request.post(`/api${path}`, {
          headers: { "X-CSRFToken": csrf },
          data,
        })
      ).ok(),
    ).toBe(true);
  }
  await post("/student/login/", {
    class_code: demo.student.class_code,
    student_number: "001",
    password: "001",
  });
  await post("/student/change-password/", { password: "Reminder!Student2026" });
  await student.reload();
  await student
    .getByRole("button", { name: "通知，1 則未查看", exact: true })
    .click();
  const inbox = student.getByRole("dialog", { name: "通知中心" });
  await inbox.getByRole("button", { name: /公告未讀提醒：/ }).click();
  await expect(inbox).toContainText("尚未確認已讀");
  await inbox.getByRole("button", { name: "確認已讀", exact: true }).click();
  await page.getByRole("button", { name: "更新已讀名單", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "目前版本已讀名單" }),
  ).toContainText("已讀 1 人");
  await page.setViewportSize({ width: 320, height: 740 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: ".local/v2-09-reminders-mobile.png",
    fullPage: true,
  });
  await context.close();
});
