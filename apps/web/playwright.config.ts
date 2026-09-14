import path from "node:path";

import { defineConfig, type ReporterDescription } from "@playwright/test";

const artifactDir = process.env.PLAYWRIGHT_ARTIFACT_DIR;
const proxyTarget = process.env.PLAYWRIGHT_PROXY_TARGET;
const reporters: ReporterDescription[] = [["list"]];

if (artifactDir) {
  reporters.push(
    ["junit", { outputFile: path.join(artifactDir, "results.xml") }],
    ["html", { outputFolder: path.join(artifactDir, "report"), open: "never" }],
  );
}

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 15_000,
  outputDir: artifactDir ? path.join(artifactDir, "test-results") : "test-results",
  webServer: proxyTarget
    ? {
        command: "node tests/ci-proxy.mjs",
        url: "http://127.0.0.1:3000/it/programs",
        reuseExistingServer: false,
        timeout: 30_000,
      }
    : undefined,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  reporter: reporters,
});
