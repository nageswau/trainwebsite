import { test, expect } from "@playwright/test";

// SEC-002 -- GDPR self-service export/delete. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.

test("signed-in user can request a data export and download it (SEC-002-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/account/privacy");
  await expect(page.getByRole("heading", { name: "Your data, your control" })).toBeVisible();

  await page.getByRole("button", { name: "Request a copy of my data" }).click();
  await expect(page.getByText("Your export is ready.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download it here" })).toBeVisible();
});

test("a deletion request blocked by a retention hold shows the real reason, not a silent failure (SEC-002-AC02)", async ({ page }) => {
  // The seeded demo student has a signed enrolment agreement (ConsentRecord from
  // STU-009), which is a real, evidence-backed retention hold -- the request must be
  // rejected with a visible reason, never silently dropped or falsely "succeeded."
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/account/privacy");
  await page.getByRole("button", { name: "Request account deletion" }).click();
  await expect(page.getByText(/We can.t delete your account yet/)).toBeVisible();
});

test("the privacy page requires authentication", async ({ page }) => {
  await page.goto("/account/privacy");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});

test("Privacy link is reachable from the signed-in header", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it");
  await page.getByRole("link", { name: "Privacy" }).click();
  await page.waitForURL("**/account/privacy");
});
