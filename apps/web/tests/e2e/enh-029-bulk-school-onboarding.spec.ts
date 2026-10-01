import { expect, test, type Page } from "@playwright/test";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ENH-029 -- bulk school onboarding through the real Admin Schools page
// (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md, AC01/AC02/AC11).
// Requires the stack with `python -m app.seed` applied (overseasadmin@edusphere.local / Demo@123). Throwaway schools per run.
const unique = Date.now();
const coordinator = (n: number) => `enh029-e2e-${n}-${unique}@example.local`;
const schoolName = (letter: string) => `E2E 029 ${letter} ${unique}`;
const csv = (lines: string[]) => Buffer.from(["name,city,coordinator_full_name,coordinator_email", ...lines].join("\n") + "\n");
const threeRows = {
  name: "schools.csv",
  mimeType: "text/csv",
  buffer: csv([
    `${schoolName("A")},Pune,Coord A,${coordinator(1)}`,
    `${schoolName("B")},Goa,Coord B,${coordinator(2)}`,
    `${schoolName("C")},Goa,Coord C,${coordinator(1)}`, // repeats row 2's coordinator email
  ]),
};

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const panelOf = (page: Page) => page.locator(".action-card", { has: page.getByRole("heading", { name: "Onboard several schools (CSV)" }) });

test("admin onboards several schools from one CSV; a new coordinator signs in (ENH-029)", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  const panel = panelOf(page);

  const [download] = await Promise.all([page.waitForEvent("download"), panel.getByRole("link", { name: /Download the template/ }).click()]);
  expect(download.suggestedFilename()).toBe("school-onboarding-bulk-template.csv");

  await panel.getByLabel("Filled-in schools file").setInputFiles(threeRows);
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/overseas-admin/schools/bulk-upload")),
    panel.getByRole("button", { name: "Upload schools" }).click(),
  ]);
  expect(response.status()).toBe(201);
  const report = await response.json();
  await expect(panel.getByRole("heading", { name: "Upload result" })).toBeFocused();
  await expect(panel.getByText("2 of 3 schools onboarded, 1 rejected", { exact: false })).toBeVisible();
  await expect(panel.getByText("same coordinator_email as row 2")).toBeVisible();
  await expect(page.getByRole("cell", { name: schoolName("A") }).first()).toBeVisible(); // Partner Schools list refreshed

  // choosing the file again is a new upload (new key): every row is now a duplicate and is rejected row by row
  await panel.getByLabel("Filled-in schools file").setInputFiles(threeRows);
  await panel.getByRole("button", { name: "Upload schools" }).click();
  await expect(panel.getByText("No schools were onboarded", { exact: false })).toBeVisible();

  await activateWithToken(page.request, report.rows[0].development_welcome_token);
  await signIn(page, coordinator(1), E2E_PASSWORD, "/school/coordinator/dashboard");
});

test("keyboard-only use and a 360 px layout without horizontal scroll (ENH-029 AC11)", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  const panel = panelOf(page);
  await panel.getByRole("button", { name: "Upload schools" }).focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("alert")).toHaveText("Choose a filled-in CSV file first.");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
