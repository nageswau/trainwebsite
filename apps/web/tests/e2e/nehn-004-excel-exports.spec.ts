import { readFile } from "node:fs/promises";

import { expect, test, type Download, type Page } from "@playwright/test";

// nehn-004 (DEC-SCOPE-280 X3, X6): every report page that downloads a CSV also downloads Excel -- the telecaller reports and
// performance, the recruiter performance, the partnership reports and the agency reports and commissions. Seeded demo accounts; the
// shared stack DB also holds backend-test rows, so the checks are on file names, the zip signature and refusals, not numbers.

const PASSWORD = "Demo@123";

async function signIn(page: Page, loginPath: string, email: string) {
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function download(page: Page, button: "Download CSV" | "Download Excel"): Promise<{ file: Download; body: Buffer }> {
  const group = page.getByRole("group", { name: /^Export / }).first();
  const pending = page.waitForEvent("download");
  await group.getByRole("button", { name: button }).click();
  const file = await pending;
  await expect(group.getByText("Report downloaded.")).toBeVisible();
  return { file, body: await readFile((await file.path())!) };
}

async function bothFormats(page: Page, csvName: RegExp) {
  const csv = await download(page, "Download CSV");
  expect(csv.file.suggestedFilename()).toMatch(csvName);
  const xlsx = await download(page, "Download Excel");
  expect(xlsx.file.suggestedFilename()).toBe(csv.file.suggestedFilename().replace(/\.csv$/, ".xlsx"));
  expect(xlsx.body.subarray(0, 2).toString()).toBe("PK"); // a zip package, not an error page saved as a file
}

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

test("a telecaller manager downloads the reports and the performance table as Excel", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page, "/admin/login", "telecaller.manager@edusphere.local");
  await page.goto("/telecaller/manager/reports?report=source");
  await bothFormats(page, /^telecaller-source-\d{4}-\d{2}-\d{2}-to-\d{4}-\d{2}-\d{2}\.csv$/);
  await page.goto("/telecaller/manager/performance");
  await bothFormats(page, /^telecaller-performance-.*\.csv$/);
  expect(errors).toEqual([]);
});

test("a telecaller is refused the Excel export too", async ({ page }) => {
  await signIn(page, "/it/login", "telecaller.it@edusphere.local");
  expect((await page.request.get("/api/v1/telecaller/reports/source.xlsx")).status()).toBe(403);
  expect((await page.request.get("/api/v1/telecaller/manager/performance.xlsx")).status()).toBe(403);
});

test("a placement manager downloads recruiter performance as Excel", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page, "/it/login", "placement.manager@edusphere.local");
  await page.goto("/recruiter/manager/performance");
  await bothFormats(page, /^recruiter-performance-.*\.csv$/);
  expect(errors).toEqual([]);
});

test("the super admin downloads a partnership report as Excel; signed out is refused", async ({ page }) => {
  expect((await page.request.get("/api/v1/partnership/reports/pipeline.xlsx")).status()).toBe(401);
  const errors = watchErrors(page);
  await signIn(page, "/admin/login", "superadmin@edusphere.local");
  await page.goto("/partnership/reports?report=pipeline");
  await bothFormats(page, /^partnership-pipeline-\d{4}-\d{2}-\d{2}\.csv$/);
  expect(errors).toEqual([]);
});

test("an agency Master downloads a report and the commissions as Excel", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page, "/overseas/login", "agent@edusphere.local");
  await page.goto("/overseas/agent/reports?report=students");
  await bothFormats(page, /^agency-students-.*\.csv$/);
  await expect(page.getByText("Up to 10,000 rows.")).toBeVisible();
  // The Commission tab offers the pair only when there is a commission to export, so the file itself is checked through the API.
  const commissions = await page.request.get("/api/v1/workflows/overseas/agent/commissions/report.xlsx");
  expect(commissions.status()).toBe(200);
  expect(commissions.headers()["content-type"]).toBe("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  expect((await commissions.body()).subarray(0, 2).toString()).toBe("PK");
  expect(errors).toEqual([]);
});

test("the two buttons fit a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "/admin/login", "telecaller.manager@edusphere.local");
  await page.goto("/telecaller/manager/reports?report=source");
  const group = page.getByRole("group", { name: /^Export / });
  for (const name of ["Download CSV", "Download Excel"]) {
    const box = (await group.getByRole("button", { name }).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(375);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
