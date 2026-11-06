import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

async function post(page: Page, path: string, data: unknown) {
  const { csrfToken } = await (await page.request.get("/api/csrf/")).json();
  const response = await page.request.post(`/api${path}`, {
    headers: { "X-CSRFToken": csrfToken },
    data,
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

function seedGrowth(id: number, animal: string, exp: number) {
  // Arrange a long-lived class; all assertions use the browser or public API.
  execFileSync(
    resolve(".venv/Scripts/python.exe"),
    [
      "backend/manage.py",
      "shell",
      "-c",
      `from core.models import Mascot; Mascot.objects.filter(cohort_id=${id}).update(animal=${JSON.stringify(animal)}, exp=${exp})`,
    ],
    { env: { ...process.env, CM_DEBUG: "1" }, windowsHide: true },
  );
}

for (const [animal, name] of [
  ["cat", "貓"],
  ["dog", "狗"],
  ["rabbit", "兔"],
  ["cow", "牛"],
  ["horse", "馬"],
  ["pig", "豬"],
]) {
  test(`${animal} farm shows only current growth, keeps mobile size and respects motion controls`, async ({
    page,
  }) => {
    test.setTimeout(180000);
    const email = `farm-${Date.now()}@example.com`;
    const password = "Teacher!Farm2026";
    await page.goto("/#login");
    await post(page, "/auth/register/", {
      email,
      password,
      display_name: "農場導師",
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
      name: "農場班",
      entry_year: 2026,
      current_grade: 1,
    });
    seedGrowth(cohort.id, animal, 0);
    await post(page, `/classes/${cohort.id}/students/`, {
      text: "1\t農場同學\t001",
    });
    const students = await (
      await page.request.get(`/api/classes/${cohort.id}/students/`)
    ).json();
    const record = await post(page, `/classes/${cohort.id}/scores/`, {
      student_id: students[0].id,
      kind: "positive",
      score: 1,
      template: "helping",
      request_id: crypto.randomUUID(),
    });
    await post(page, `/classes/${cohort.id}/point-awards/`, {
      request_id: crypto.randomUUID(),
      items: [{ record_id: record.id, revision: 1, points: 5 }],
    });
    await post(page, "/auth/logout/", {});
    await post(page, "/student/login/", {
      class_code: cohort.student_login_code,
      student_number: "001",
      password: "001",
    });
    await post(page, "/student/change-password/", {
      password: "Student!Farm2026",
    });
    await page.reload();
    await page.getByRole("button", { name: "餵食班級吉祥物" }).click();
    await expect(
      page.getByRole("img", { name: /農場中的.*幼年/ }),
    ).toBeVisible();
    await expect(page.getByText("幼年", { exact: true })).toBeVisible();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(page.getByRole("button", { name: "動一動" })).toBeVisible();
    const traveller = page.locator(".farm-traveller");
    expect(await traveller.evaluate((el) => el.getAnimations().length)).toBe(0);
    await page.getByRole("button", { name: "動一動" }).click();
    await expect
      .poll(() => traveller.evaluate((el) => el.getAnimations()[0]?.playState))
      .toBe("running");
    // Seek within the real CSS travel cycle, then observe actual pixel displacement.
    await traveller.evaluate((el) => {
      el.getAnimations()[0].currentTime = 3500;
    });
    const startX = (await traveller.boundingBox())!.x;
    await expect
      .poll(async () => Math.abs((await traveller.boundingBox())!.x - startX))
      .toBeGreaterThan(2);
    await page.getByRole("button", { name: "休息一下" }).click();
    expect(await traveller.evaluate((el) => el.getAnimations().length)).toBe(0);

    const levels = [
      [0, 1, "幼年", "1.00"],
      [600, 4, "幼年", "1.09"],
      [1000, 5, "成長期", "1.12"],
      [3600, 9, "成長期", "1.24"],
      [4500, 10, "成熟", "1.27"],
      [19000, 20, "成熟", "1.57"],
      [21000, 21, "成熟", "1.60"],
      [23100, 22, "成熟", "1.60"],
    ] as const;
    for (const [exp, level, stage, scale] of levels) {
      seedGrowth(cohort.id, animal, exp);
      await page.getByRole("button", { name: "重新整理吉祥物" }).click();
      await expect(
        page.getByRole("heading", { name: `${name}夥伴 · Lv.${level}` }),
      ).toBeVisible();
      await expect(page.getByText(stage, { exact: true })).toBeVisible();
      await expect(
        page.getByRole("img", { name: `農場中的${name} · ${stage}` }),
      ).toBeVisible();
      await expect(page.locator(".farm-actor svg")).toHaveCount(1);
      for (const width of [320, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        const bounds = await page.locator(".mascot-farm").boundingBox();
        const art = await page.locator(".farm-size").boundingBox();
        expect(art!.width).toBeCloseTo(
          (width === 320 ? 112 : 140) * Number(scale),
          0,
        );
        expect(art!.x).toBeGreaterThanOrEqual(bounds!.x);
        expect(art!.x + art!.width).toBeLessThanOrEqual(
          bounds!.x + bounds!.width,
        );
        expect(art!.y).toBeGreaterThanOrEqual(bounds!.y);
        expect(art!.y + art!.height).toBeLessThanOrEqual(
          bounds!.y + bounds!.height,
        );
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        if ([1, 5, 10, 21].includes(level))
          await page.screenshot({
            path: `.local/v2-05-${animal}-${level}-${width}.png`,
            fullPage: true,
          });
      }
    }
    await page.getByRole("button", { name: "動一動" }).click();
    for (const [exp, level, label] of [
      [999, 5, "成長期"],
      [4499, 10, "成熟"],
      [20999, 21, "成熟"],
      [23099, 22, "成熟"],
    ] as const) {
      seedGrowth(cohort.id, animal, exp);
      await page.getByRole("button", { name: "重新整理吉祥物" }).click();
      await expect(
        page.getByText(`累積總餵食量 ${exp} exp`, { exact: true }),
      ).toBeVisible();
      await expect(page.locator(".farm-treat")).toHaveCSS("opacity", "0");
      await page.getByRole("button", { name: "確認餵食", exact: true }).click();
      await expect(page.locator(".farm-treat")).toHaveCSS("opacity", "1");
      await expect(
        page.getByRole("heading", { name: `${name}夥伴 · Lv.${level}` }),
      ).toBeVisible();
      await expect(page.getByText(label, { exact: true })).toBeVisible();
      if (level === 5) {
        // The feeding reaction should still be visible beyond the former two seconds.
        await page.waitForTimeout(2500);
        await expect(page.locator(".farm-treat")).toHaveCSS("opacity", "1");
      }
      await expect(page.locator(".farm-treat")).toHaveCSS("opacity", "0");
    }
    await page.getByRole("button", { name: "休息一下" }).click();
    await page.getByRole("button", { name: "動一動" }).click();
    await expect(page.getByRole("button", { name: "休息一下" })).toBeVisible();
    expect(
      await page
        .locator(".farm-treat")
        .evaluate((el) => getComputedStyle(el).opacity),
    ).toBe("0");

    // Simulate the browser visibility event; hidden pages pause CSS work and do
    // not replay the last successful feeding when made visible again.
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", {
        configurable: true,
        value: true,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await expect
      .poll(() => traveller.evaluate((el) => el.getAnimations()[0]?.playState))
      .toBe("paused");
    await page.evaluate(() => {
      Reflect.deleteProperty(document, "hidden");
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await expect
      .poll(() => traveller.evaluate((el) => el.getAnimations()[0]?.playState))
      .toBe("running");
    expect(
      await page
        .locator(".farm-treat")
        .evaluate((el) => getComputedStyle(el).opacity),
    ).toBe("0");

    // A failed artwork chunk must not disable the genuine feeding API or numbers.
    await page.route("**/*MascotArtwork*", (route) => route.abort("failed"));
    await page.reload();
    await page.getByRole("button", { name: "餵食班級吉祥物" }).click();
    await expect(
      page.getByText("仍可餵食與查看成長", { exact: false }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "動一動" })).toBeVisible();
    await page.getByRole("button", { name: "確認餵食", exact: true }).click();
    await expect(
      page.getByText("餵食成功，班級吉祥物增加 1 exp。", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("累積總餵食量 23101 exp", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("今日還可餵 0 點", { exact: true }),
    ).toBeVisible();
  });
}
