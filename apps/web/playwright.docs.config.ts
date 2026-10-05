import { defineConfig } from "@playwright/test";

// Documentation screenshot capture only (docs/documentation-plan.md S2.3) -- not part of the e2e suite.
// Run: npx playwright test -c playwright.docs.config.ts [spec]   (from apps/web)
export default defineConfig({
  testDir: "./tests/doc-capture",
  testMatch: "**/*.capture.ts",
  workers: 1,
  retries: 0,
  timeout: 60_000,
  outputDir: "test-results/doc-capture",
  reporter: [["list"]],
  use: {
    baseURL: process.env.DOCS_BASE_URL || "http://localhost:3000",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
  },
});
