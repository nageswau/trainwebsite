import { test, expect } from "@playwright/test";

// ADM-009 -- Resources/recordings oversight. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds one resource,
// "FastAPI API Design Notes", against trainer Meera Iyer's batch).

async function loginAsItAdmin(page: import("@playwright/test").Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
}

test("IT Admin sees resources across every trainer's batches, not just one (ADM-009-AC01)", async ({ page }) => {
  await loginAsItAdmin(page);
  await page.goto("/it/admin/resources");
  await expect(page.getByRole("heading", { name: "Resources & Recordings" })).toBeVisible();

  // The generic DataTable paginates client-side (RAID.md I-07) -- the shared dev DB has
  // accumulated enough test-created resources that the seeded row can sit past page 1.
  // Search to it first rather than asserting on the raw unpaginated list.
  await page.getByLabel("Search records").fill("FastAPI API Design Notes");
  await expect(page.getByText("FastAPI API Design Notes")).toBeVisible();
  await expect(page.getByText("Meera Iyer")).toBeVisible();
});

test("the resources oversight page requires authentication", async ({ page }) => {
  await page.goto("/it/admin/resources");
  await expect(page).toHaveURL(/\/it\/login/);
});
