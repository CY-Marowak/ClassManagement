import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.use({ actionTimeout: 10000 });

test("generated demo supports login, dashboard tasks, scoring, awarding, feeding and role isolation", async ({
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
  async function login(target: Page, role: string) {
    await target.goto("/#login");
    await target
      .getByLabel("Email", { exact: true })
      .fill(demo.teachers[role].email);
    await target
      .getByLabel("密碼", { exact: true })
      .fill(demo.teachers[role].password);
    await target.getByRole("button", { name: "登入班級日常" }).click();
    await expect(
      target.getByRole("heading", { name: "我的班級", exact: true }),
    ).toBeVisible();
  }
  await login(page, "homeroom");
  await expect(page.locator(".class-card")).toHaveCount(1);
  await page.getByRole("button", { name: "工作首頁", exact: true }).click();
  await expect(page.getByRole("button", { name: /待審教師/ })).toContainText(
    "1",
  );
  await page.getByRole("button", { name: /待審教師/ }).click();
  await page.getByRole("button", { name: "批准", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("教師狀態已更新");
  await page.getByRole("button", { name: /返回工作首頁/ }).click();
  await expect(page.getByRole("button", { name: /待審教師/ })).toContainText(
    "0",
  );
  await page.getByRole("button", { name: "開始記分" }).click();
  await page
    .getByLabel("記分學生", { exact: true })
    .selectOption({ label: "1 號 · 展示小晴（總分 1）" });
  await page.getByLabel("分數", { exact: true }).fill("3");
  await page.getByLabel("補充原因（選填）").fill("展示流程獎勵");
  await page.getByRole("button", { name: "送出記分", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已記錄" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /返回工作首頁/ }).click();
  await expect(
    page.getByRole("region", { name: "最近十筆記分" }),
  ).toContainText("展示流程獎勵");
  await page.getByRole("button", { name: "查看全部分數紀錄 →" }).click();
  await expect(
    page.locator(".score-record").filter({ hasText: "展示流程獎勵" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /返回工作首頁/ }).click();
  await page.getByRole("button", { name: "發點數", exact: true }).click();
  const source = page
    .locator(".score-record")
    .filter({ hasText: "展示流程獎勵" });
  await source.getByRole("checkbox").check();
  await source.getByLabel("展示小晴的發放點數").fill("3");
  await page.getByRole("button", { name: "發放所選點數" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "發放" }),
  ).toBeVisible();

  const studentContext = await browser.newContext();
  const student = await studentContext.newPage();
  await student.goto(`/#student-login?class=${demo.student.class_code}`);
  await student.getByLabel("學號", { exact: true }).fill("001");
  await student.getByLabel("密碼", { exact: true }).fill("001");
  await student.getByRole("button", { name: "學生登入", exact: true }).click();
  await student
    .getByLabel("新密碼", { exact: true })
    .fill("Demo!StudentGarden2026");
  await student.getByLabel("確認新密碼").fill("Demo!StudentGarden2026");
  await student.getByRole("button", { name: "儲存密碼並進入班級" }).click();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toContainText("可用點數 3");
  await expect(
    student.getByText("一起照顧班級吉祥物", { exact: true }),
  ).toBeVisible();
  await student.getByRole("button", { name: "餵食班級吉祥物" }).click();
  await student.getByLabel("餵食點數").selectOption("2");
  await student.getByRole("button", { name: "確認餵食", exact: true }).click();
  await expect(student.getByText("可用點數 1", { exact: true })).toBeVisible();
  await expect(
    student.getByText("累積總餵食量 2 exp", { exact: true }),
  ).toBeVisible();
  expect(
    (
      await student.request.get(`/api/classes/${demo.cohort.id}/dashboard/`)
    ).status(),
  ).toBe(403);

  const coContext = await browser.newContext();
  const co = await coContext.newPage();
  await login(co, "coTeacher");
  await expect(
    co.getByRole("button", { name: "工作首頁", exact: true }),
  ).toHaveCount(0);
  await co.getByRole("button", { name: "班級公告", exact: true }).click();
  await co.getByRole("button", { name: "留言（1）", exact: true }).click();
  await expect(co.locator(".comment-card")).toContainText(
    "記得先完成自己的學習任務",
  );
  expect(
    (
      await co.request.get(`/api/classes/${demo.cohort.id}/dashboard/`)
    ).status(),
  ).toBe(404);
  expect(
    (
      await co.request.get(`/api/classes/${demo.cohort.id}/import-issues/`)
    ).status(),
  ).toBe(404);
  const otherContext = await browser.newContext();
  const other = await otherContext.newPage();
  await login(other, "other");
  await expect(other.locator(".class-card")).toContainText(
    demo.other_cohort.name,
  );
  expect(
    (
      await other.request.get(`/api/classes/${demo.cohort.id}/dashboard/`)
    ).status(),
  ).toBe(404);
  await studentContext.close();
  await coContext.close();
  await otherContext.close();
});
