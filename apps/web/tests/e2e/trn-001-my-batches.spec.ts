import { test, expect } from "@playwright/test";

// TRN-001 -- My Batches. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied (seeds the demo trainer's own batch).

test("trainer sees their own assigned batch, scoped to them (TRN-001-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await expect(page.getByRole("heading", { name: "Trainer Dashboard" })).toBeVisible();
  await expect(page.getByText("Assigned batches", { exact: true })).toBeVisible();
  await expect(page.locator("table")).toContainText("PY-FS-AUG-2026");
});

test("the trainer batch list requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/dashboard");
  await expect(page).toHaveURL(/\/it\/login/);
});
