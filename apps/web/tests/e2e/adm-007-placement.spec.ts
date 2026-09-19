import { test, expect } from "@playwright/test";

// ADM-007 -- Placement Team workspace. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.

test("placement team withdraws a candidate from the active pool (ADM-007-AC02)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  // A fresh, throwaway candidate created via the real admin API -- never withdraw the
  // shared seeded demo student, which other specs may depend on staying in the pool.
  const uniqueName = `ADM-007 Candidate ${Date.now()}`;
  const created = await page.request.post("/api/v1/admin/users", {
    data: { role: "it_student", email: `adm007-${Date.now()}@example.com`, full_name: uniqueName },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/it/login");
  await page.fill("#login-email", "placement@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/placement/dashboard");

  await page.goto("/it/placement/candidates");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Candidate pool" }) });
  await panel.getByLabel("Search by name or email").fill(uniqueName);
  const row = panel.locator("tr", { hasText: uniqueName });
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: "Withdraw from pool" }).click();
  await expect(panel.getByText("No candidates match this search.")).toBeVisible();
});

test("placement candidate pool requires authentication", async ({ page }) => {
  await page.goto("/it/placement/candidates");
  await expect(page).toHaveURL(/\/it\/login/);
});
