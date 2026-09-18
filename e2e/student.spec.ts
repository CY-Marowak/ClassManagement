import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("teacher imports and corrects roster; student changes password, keeps avatar and loses access after deletion", async ({
  page,
  browser,
}) => {
  test.setTimeout(120000);
  const email = `roster-${Date.now()}@example.com`;
  const password = "Teacher!Browser2026";
  await page.goto("/#register");
  await page.getByLabel("顯示名稱").fill("林老師");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "建立帳號並寄送驗證信" }).click();
  await expect(page.getByRole("status")).toBeVisible();
  const python = resolve(
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
  const link = execFileSync(python, ["scripts/read-mail.py", email, "verify"], {
    encoding: "utf8",
    windowsHide: true,
  }).trim();
  await page.goto(link);
  await page.getByRole("button", { name: "確認驗證 Email" }).click();
  await expect(page.getByRole("status")).toContainText("驗證完成");
  await page.getByRole("link", { name: "返回登入" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("密碼", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登入班級日常" }).click();
  await page.getByRole("button", { name: "建立第一個班級" }).click();
  await page.getByLabel("班級名稱").fill("星光班");
  await page.getByRole("button", { name: "建立班級", exact: true }).click();
  await page.getByRole("button", { name: "學生名單" }).click();
  const rows = Array.from(
    { length: 28 },
    (_, i) => `${i + 1}\t同學${i + 1}\t${String(i + 1).padStart(5, "0")}`,
  );
  await page
    .getByLabel("貼上學生名單")
    .fill(rows.join("\n") + "\n29\t缺欄\n30\t衝突\t00001");
  await page.getByRole("button", { name: "匯入名單", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "新增 28 · 略過 0 · 待修正 2",
    { timeout: 30000 },
  );
  await page
    .getByLabel("貼上學生名單")
    .fill("29\t同學29\t00029\n30\t同學30\t00030");
  await page.getByRole("button", { name: "匯入名單", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "新增 2 · 略過 0 · 待修正 0",
  );
  await expect(
    page.getByRole("table", { name: "學生名單" }).getByRole("row"),
  ).toHaveCount(31);
  const studentLink = await page.getByLabel("學生登入連結").inputValue();
  await page.screenshot({ path: ".local/roster-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: ".local/roster-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  const context = await browser.newContext();
  const student = await context.newPage();
  await student.goto(studentLink);
  await expect(student.getByLabel("班級登入碼")).not.toHaveValue("");
  await student.getByLabel("學號", { exact: true }).fill("00001");
  await student.getByLabel("密碼", { exact: true }).fill("00001");
  await student.getByRole("button", { name: "學生登入", exact: true }).click();
  await expect(
    student.getByRole("heading", { name: "設定自己的密碼" }),
  ).toBeVisible();
  await student.goto("/#classes");
  await student.reload();
  await expect(
    student.getByRole("heading", { name: "設定自己的密碼" }),
  ).toBeVisible();
  await student
    .getByLabel("新密碼", { exact: true })
    .fill("Meadow!Journey2026");
  await student.getByLabel("確認新密碼").fill("Meadow!Journey2026");
  await student.getByRole("button", { name: "儲存密碼並進入班級" }).click();
  await expect(
    student.getByRole("heading", { name: "同學1", exact: true }),
  ).toBeVisible();
  await expect(student.getByText("星光班", { exact: true })).toBeVisible();
  await expect(student.getByText("同學2", { exact: true })).toHaveCount(0);
  const avatar = await student.getByRole("img").getAttribute("aria-label");
  await student.screenshot({
    path: ".local/student-desktop.png",
    fullPage: true,
  });
  await student.setViewportSize({ width: 390, height: 844 });
  await student.screenshot({
    path: ".local/student-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await student.getByRole("button", { name: "登出", exact: true }).click();
  await expect(
    student.getByRole("button", { name: "學生登入", exact: true }),
  ).toBeVisible();
  await student.goto(studentLink);
  await expect(student.getByLabel("班級登入碼")).not.toHaveValue("");
  await student.getByLabel("學號", { exact: true }).fill("00001");
  await student.getByLabel("密碼", { exact: true }).fill("Meadow!Journey2026");
  await student.getByRole("button", { name: "學生登入", exact: true }).click();
  await expect(student.getByRole("img")).toHaveAttribute("aria-label", avatar!);
  const roster = page.getByRole("table", { name: "學生名單" });
  await roster
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: "00001", exact: true }) })
    .getByRole("button", { name: "修改資料" })
    .click();
  const edit = page.getByRole("dialog", { name: "修改學生資料" });
  await edit.getByLabel("姓名", { exact: true }).fill("林小明");
  await edit.getByLabel("座號", { exact: true }).fill("2");
  await edit.getByRole("button", { name: "儲存修改" }).click();
  await expect(edit.getByRole("alert")).toContainText("已被其他學生使用");
  await edit.getByLabel("座號", { exact: true }).fill("31");
  await edit.getByLabel("學號", { exact: true }).fill("00901");
  await page.screenshot({
    path: ".local/student-edit-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: ".local/student-edit-desktop.png",
    fullPage: true,
  });
  await edit.getByRole("button", { name: "儲存修改" }).click();
  await expect(edit).toHaveCount(0);
  await student.reload();
  await expect(
    student.getByRole("heading", { name: "林小明", exact: true }),
  ).toBeVisible();
  await expect(student.getByRole("img")).toHaveAttribute("aria-label", avatar!);
  const editedRow = roster.getByRole("row").filter({ hasText: "00901" });
  await editedRow.getByRole("button", { name: "重設密碼" }).click();
  const reset = page.getByRole("dialog", { name: "重設學生密碼" });
  await expect(reset).toContainText("林小明");
  await reset.getByRole("button", { name: "取消" }).click();
  await student.reload();
  await expect(
    student.getByRole("heading", { name: "林小明", exact: true }),
  ).toBeVisible();
  await editedRow.getByRole("button", { name: "重設密碼" }).click();
  await page.screenshot({
    path: ".local/student-reset-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/student-reset-mobile.png",
    fullPage: true,
  });
  await reset.getByRole("button", { name: "確認重設密碼" }).click();
  await expect(reset).toHaveCount(0);
  await student.reload();
  await expect(
    student.getByRole("heading", { name: "林小明", exact: true }),
  ).toHaveCount(0);
  await student.goto(studentLink);
  await student.getByLabel("學號", { exact: true }).fill("00901");
  await student.getByLabel("密碼", { exact: true }).fill("00901");
  await student.getByRole("button", { name: "學生登入", exact: true }).click();
  await expect(
    student.getByRole("heading", { name: "設定自己的密碼" }),
  ).toBeVisible();
  await student
    .getByLabel("新密碼", { exact: true })
    .fill("Another!Journey2026");
  await student.getByLabel("確認新密碼").fill("Another!Journey2026");
  await student.getByRole("button", { name: "儲存密碼並進入班級" }).click();
  await expect(
    student.getByRole("heading", { name: "林小明", exact: true }),
  ).toBeVisible();
  await expect(student.getByRole("img")).toHaveAttribute("aria-label", avatar!);
  await page.getByRole("button", { name: "操作紀錄", exact: true }).click();
  const history = page.getByRole("region", { name: "學生操作紀錄" });
  await expect(
    history.getByRole("heading", { name: "重設密碼", exact: true }),
  ).toBeVisible();
  await expect(history).toContainText("小明");
  await expect(history).toContainText("00001 → 00901");
  await history.screenshot({ path: ".local/student-audit-mobile.png" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await history.screenshot({ path: ".local/student-audit-desktop.png" });
  await history.getByRole("button", { name: "下一頁" }).click();
  await expect(history).toContainText("第 2 頁");
  await expect(history.getByRole("button", { name: "下一頁" })).toBeDisabled();
  await page.getByRole("button", { name: "返回我的班級" }).click();
  await page.getByRole("button", { name: "編輯班級" }).click();
  await page.getByRole("button", { name: "永久刪除班級", exact: true }).click();
  await page.getByLabel("輸入完整班級名稱").fill("星光班");
  await page.getByRole("button", { name: "確認永久刪除" }).click();
  await expect(page.getByRole("status")).toContainText("已永久刪除");
  await student.reload();
  await expect(
    student.getByRole("heading", { name: "林小明", exact: true }),
  ).toHaveCount(0);
  await context.close();
});
