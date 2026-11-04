import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";

for (const outcome of ["success", "failure"] as const) {
  test(`late initial notification ${outcome} cannot undo all viewed`, async ({
    page,
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
    async function post(path: string, data: unknown) {
      const { csrfToken } = await (await page.request.get("/api/csrf/")).json();
      const response = await page.request.post(`/api${path}`, {
        headers: { "X-CSRFToken": csrfToken },
        data,
      });
      expect(response.ok()).toBe(true);
      return response.json();
    }
    await post("/auth/login/", demo.teachers.coTeacher);
    const base = `/classes/${demo.cohort.id}/announcements/`;
    const item = (await (await page.request.get(`/api${base}`)).json())
      .results[0];
    await post(base + `${item.id}/comments/`, {
      request_id: randomUUID(),
      body: item.body,
    });
    await post("/auth/logout/", {});
    await post("/auth/login/", demo.teachers.homeroom);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let captured = 0;
    let delivered = 0;
    await page.route(/\/api\/notifications\/$/, async (route) => {
      const response = await route.fetch();
      captured++;
      await gate;
      if (outcome === "success") await route.fulfill({ response });
      else
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"detail":"temporarily unavailable"}',
        });
      delivered++;
    });
    await page.reload();
    // Hold initial responses while the user opens and marks the inbox viewed.
    await expect.poll(() => captured).toBeGreaterThan(0);
    await page
      .getByRole("button", { name: "通知，未讀數尚未載入", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "通知中心" });
    await expect(dialog).toContainText("1 則未查看");
    await dialog
      .getByRole("button", { name: "全部已查看", exact: true })
      .click();
    await expect(dialog).toContainText("0 則未查看");
    release();
    await expect.poll(() => delivered).toBe(captured);
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(dialog).toContainText("0 則未查看");
    await dialog.getByRole("button", { name: "關閉通知" }).click();
    await expect(
      page.getByRole("button", { name: "通知，0 則未查看", exact: true }),
    ).toBeVisible();
  });
}
