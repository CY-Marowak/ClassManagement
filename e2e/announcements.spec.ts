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

test("homeroom publishes rich text and student reads announcement before points", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  const email = `announcement-${Date.now()}@example.com`;
  const password = "Teacher!Announcement2026";
  await page.goto("/#login");
  await post(page, "/auth/register/", {
    email,
    password,
    display_name: "公告導師",
  });
  const link = execFileSync(
    resolve(".venv/Scripts/python.exe"),
    ["scripts/read-mail.py", email, "verify"],
    { encoding: "utf8", windowsHide: true },
  ).trim();
  await post(page, "/auth/verify/", {
    token: new URLSearchParams(new URL(link).hash.split("?")[1]).get("token"),
  });
  await post(page, "/auth/login/", { email, password });
  const cohort = await post(page, "/classes/", {
    name: "公告班",
    entry_year: 2026,
    current_grade: 1,
  });
  await post(page, `/classes/${cohort.id}/students/`, { text: "1\t小明\t001" });
  await page.reload();
  await page.getByRole("button", { name: "班級公告", exact: true }).click();
  await page.getByRole("button", { name: "新增公告", exact: true }).click();
  await page.getByLabel("公告標題").fill("戶外教學");
  const editor = page.getByRole("textbox", { name: "公告內文" });
  await editor.click();
  await editor.evaluate((el) => {
    let html = "<p>明天帶水壺</p>";
    for (let i = 0; i < 7; i++)
      html = `<ul><li><p>外部文章</p>${html}</li></ul>`;
    const clipboardData = new DataTransfer();
    clipboardData.setData("text/html", html);
    el.dispatchEvent(
      new ClipboardEvent("paste", {
        clipboardData,
        bubbles: true,
        cancelable: true,
      }),
    );
  });
  await page.getByRole("button", { name: "發布公告", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("全選內文");
  await expect(page.getByRole("alert")).toContainText("清除格式");
  await editor.click();
  await editor.press("ControlOrMeta+a");
  await page.getByRole("button", { name: "清除格式", exact: true }).click();
  await page.getByRole("button", { name: "發布公告", exact: true }).click();
  await expect(page.locator(".announcement-card")).toContainText("明天帶水壺");
  await page
    .locator(".announcement-card")
    .getByRole("button", { name: "刪除", exact: true })
    .click();
  await page.getByRole("button", { name: "確認刪除公告", exact: true }).click();
  await expect(page.locator(".announcement-card")).toHaveCount(0);
  await page.getByRole("button", { name: "新增公告", exact: true }).click();
  await page.getByLabel("公告標題").fill("戶外教學");
  await editor.fill("明天帶水壺");
  await editor.press("ControlOrMeta+a");
  await page.getByRole("button", { name: "粗體", exact: true }).click();
  await page.getByRole("button", { name: "斜體", exact: true }).click();
  await page.getByRole("button", { name: "底線", exact: true }).click();
  await page.getByLabel("字體大小").selectOption("20px");
  await page.getByLabel("文字顏色").selectOption("#b42318");
  await expect(editor.locator("em")).toHaveCSS("font-synthesis", "style");
  await page.screenshot({
    path: ".local/10-editor-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "發布公告", exact: true }).click();
  const card = page.locator(".announcement-card").first();
  await expect(card).toContainText("戶外教學");
  await expect(card.locator(".announcement-body span")).toHaveCSS(
    "color",
    "rgb(180, 35, 24)",
  );
  await expect(card.locator(".announcement-body span")).toHaveCSS(
    "font-size",
    "20px",
  );
  for (const tag of ["strong", "em", "u"])
    await expect(card.locator(tag)).toHaveText("明天帶水壺");
  await expect(card.locator("em")).toHaveCSS("font-synthesis", "style");
  await card.getByRole("button", { name: "置頂", exact: true }).click();
  await expect(card.getByText("置頂", { exact: true })).toBeVisible();
  const context = await browser.newContext();
  const student = await context.newPage();
  await student.goto("/#student-login");
  await post(student, "/student/login/", {
    class_code: cohort.student_login_code,
    student_number: "001",
    password: "001",
  });
  await post(student, "/student/change-password/", {
    password: "Student!Announcement2026",
  });
  await student.reload();
  await expect(student.locator(".announcement-card")).toContainText(
    "明天帶水壺",
  );
  await expect(student.getByRole("button", { name: "新增公告" })).toHaveCount(
    0,
  );
  expect(
    await student
      .locator(".announcements")
      .evaluate(
        (el) =>
          !!(
            el.compareDocumentPosition(
              document.querySelector(".student-points")!,
            ) & Node.DOCUMENT_POSITION_FOLLOWING
          ),
      ),
  ).toBe(true);
  await student.setViewportSize({ width: 390, height: 844 });
  await post(page, `/classes/${cohort.id}/announcements/`, {
    title: "另一則公告",
    body: {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [{ type: "text", text: "另一則的內容" }],
        },
      ],
    },
    request_id: crypto.randomUUID(),
  });
  await student.reload();
  await student
    .getByRole("button", { name: "閱讀公告：戶外教學", exact: true })
    .click();
  await expect(student.locator(".announcement-card:visible")).toHaveCount(1);
  await expect(student.locator(".announcement-card:visible")).toContainText(
    "明天帶水壺",
  );
  await expect(student.getByText("另一則的內容", { exact: true })).toBeHidden();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toBeHidden();
  await expect(
    student.getByRole("button", { name: "← 返回公告清單", exact: true }),
  ).toBeFocused();
  await student.screenshot({
    path: ".local/13-announcement-detail-mobile.png",
    fullPage: true,
  });
  await student
    .getByRole("button", { name: "← 返回公告清單", exact: true })
    .click();
  await expect(student.locator(".announcement-card")).toHaveCount(2);
  await expect(
    student.getByRole("button", { name: "閱讀公告：戶外教學", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "重新載入公告", exact: true }).click();
  await page
    .getByRole("button", { name: "閱讀公告：戶外教學", exact: true })
    .click();
  await expect(page.locator(".announcement-card:visible")).toHaveCount(1);
  await expect(page.getByText("另一則的內容", { exact: true })).toBeHidden();
  await page.screenshot({
    path: ".local/13-announcement-detail-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "← 返回公告清單", exact: true })
    .click();
  // Remove only the extra test announcement to continue the original workflow.
  const extra = page
    .locator(".announcement-card")
    .filter({ hasText: "另一則公告" });
  await extra.getByRole("button", { name: "刪除", exact: true }).click();
  await page.getByRole("button", { name: "確認刪除公告", exact: true }).click();
  await expect(extra).toHaveCount(0);
  await student
    .getByRole("button", { name: "重新載入公告", exact: true })
    .click();
  await expect(student.locator(".announcement-card")).toHaveCount(1);
  const announcements = student.getByRole("region", {
    name: "班級公告",
    exact: true,
  });
  await announcements
    .getByRole("button", { name: "全部收合", exact: true })
    .click();
  await expect(
    announcements.getByRole("button", { name: "全部展開", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(student.locator(".announcement-card")).toBeHidden();
  await expect(
    student.getByRole("region", { name: "我的點數", exact: true }),
  ).toBeVisible();
  await expect(student.locator(".score-total")).toBeVisible();
  await student.screenshot({
    path: ".local/12-announcements-collapsed-mobile.png",
    fullPage: true,
  });
  await announcements
    .getByRole("button", { name: "全部展開", exact: true })
    .click();
  await expect(student.locator(".announcement-card")).toBeVisible();
  await expect(
    announcements.getByRole("button", { name: "全部收合", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await student.screenshot({
    path: ".local/10-home-mobile.png",
    fullPage: true,
  });
  expect(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "閱讀公告：戶外教學", exact: true })
    .click();
  await card.getByRole("button", { name: "編輯", exact: true }).click();
  await page.getByLabel("公告標題").fill("戶外教學更新");
  await editor.click();
  await editor.press("ControlOrMeta+a");
  await page.getByRole("button", { name: "清除格式", exact: true }).click();
  await page.getByRole("button", { name: "項目符號", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: ".local/10-editor-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const changeUrl = `**/api/classes/${cohort.id}/announcements/*/`;
  await page.route(
    changeUrl,
    async (route) => {
      const response = await route.fetch();
      expect(response.ok()).toBe(true);
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "儲存公告", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("公告標題")).toHaveValue("戶外教學更新");
  await expect(page.getByLabel("公告標題")).toBeDisabled();
  await page.getByRole("button", { name: "重試這次操作", exact: true }).click();
  await expect(card).toContainText("已編輯");
  await expect(card.locator(".announcement-body ul li")).toHaveText(
    "明天帶水壺",
  );
  await expect(card.locator(".announcement-body strong")).toHaveCount(0);
  await card.getByRole("button", { name: "編輯", exact: true }).click();
  await editor.click();
  await editor.press("ControlOrMeta+a");
  await page.getByRole("button", { name: "編號清單", exact: true }).click();
  await editor.press("End");
  await editor.press("Enter");
  await editor.evaluate((el) => {
    const clipboardData = new DataTransfer();
    clipboardData.setData(
      "text/html",
      '<span style="font-size:99px;color:purple" onclick="alert(1)">貼上文字</span><img src=x><a href="https://example.com">連結文字</a>',
    );
    el.dispatchEvent(
      new ClipboardEvent("paste", {
        clipboardData,
        bubbles: true,
        cancelable: true,
      }),
    );
  });
  await page.getByRole("button", { name: "儲存公告", exact: true }).click();
  await expect(card.locator(".announcement-body ol li")).toHaveCount(2);
  await expect(card).toContainText("貼上文字連結文字");
  await expect(
    card.locator(".announcement-body a, .announcement-body img"),
  ).toHaveCount(0);
  await card.getByRole("button", { name: "編輯", exact: true }).click();
  await editor.click();
  await editor.press("ControlOrMeta+End");
  await page.getByRole("button", { name: "粗體", exact: true }).click();
  await editor.press("Shift+Enter");
  await editor.pressSequentially("換行文字");
  await page.getByRole("button", { name: "儲存公告", exact: true }).click();
  await expect(
    card
      .locator(".announcement-body p")
      .filter({ hasText: "換行文字" })
      .locator("br"),
  ).toHaveCount(1);
  await expect(card).toContainText("換行文字");
  await card.getByRole("button", { name: "編輯", exact: true }).click();
  const latest = (
    await (
      await page.request.get(`/api/classes/${cohort.id}/announcements/`)
    ).json()
  ).results[0];
  await post(page, `/classes/${cohort.id}/announcements/${latest.id}/`, {
    action: "pin",
    revision: latest.revision,
    is_pinned: false,
    request_id: crypto.randomUUID(),
  });
  await page.getByLabel("公告標題").fill("舊視窗不可覆蓋");
  await page.getByRole("button", { name: "儲存公告", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("公告已變更");
  await page.getByRole("button", { name: "捨棄舊操作並重新載入公告" }).click();
  await expect(card).toContainText("戶外教學更新");
  await card.getByRole("button", { name: "刪除", exact: true }).click();
  await page.route(
    `**/api/classes/${cohort.id}/announcements/?page=1`,
    (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "測試讀取失敗" }),
      }),
    { times: 1 },
  );
  await page.getByRole("button", { name: "確認刪除公告", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("公告操作已完成");
  await expect(page.getByRole("button", { name: "確認刪除公告" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "重新載入公告", exact: true }).click();
  await expect(page.locator(".announcement-card")).toHaveCount(0);
  await student.reload();
  await expect(student.getByText("目前沒有公告。")).toBeVisible();
  await context.close();
});
