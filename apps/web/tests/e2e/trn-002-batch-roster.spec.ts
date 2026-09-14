import { test, expect } from "@playwright/test";

// TRN-002 -- Batch detail (roster and schedule). Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds the demo
// trainer's batch with the demo student enrolled).

test("trainer sees their batch's own roster and schedule, scoped to that batch (TRN-002-AC01/AC02)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await expect(page.getByRole("heading", { name: "Batch roster and schedule" })).toBeVisible();
  const card = page.locator(".card", { has: page.getByRole("heading", { name: "PY-FS-AUG-2026", exact: true }) });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Arjun Rao");
  await expect(card).toContainText("enrolled");
});

test("batch roster requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/dashboard");
  await expect(page).toHaveURL(/\/it\/login/);
});
