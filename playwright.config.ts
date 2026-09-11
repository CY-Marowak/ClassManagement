import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 45000,
  outputDir: `.local/playwright-results-${Date.now()}`,
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "node scripts/backend.mjs",
      url: "http://127.0.0.1:8000/api/csrf/",
      reuseExistingServer: true,
    },
    {
      command: "npm --prefix frontend run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
    },
  ],
});
