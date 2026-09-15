import { test, expect } from "@playwright/test";

// ADM-012 -- Roles/permission administration. PARTIAL scope, deliberately: the confirmed
// requirement (PRD-ADM-013) is view-only ("Admin can view role/permission assignments");
// runtime editing was never confirmed and is not built (see the backend test file's own
// docstring). Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied.

test("IT Admin views the real, live permission bundle per role (ADM-012-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/roles");
  await expect(page.getByRole("heading", { name: "Roles & Permissions" })).toBeVisible();
  // Real data straight from core/rbac.py -- not a fabricated/hand-copied table. The
  // table paginates client-side at 10 rows/page (RAID.md I-07); with 19 roles now
  // catalogued (School-domain roles added several more), a bare getByText can land on
  // page 2 -- search first, same fix pattern used elsewhere in this suite.
  await page.getByLabel("Search records").fill("super_admin");
  await expect(page.getByText("super_admin")).toBeVisible();
  await page.getByLabel("Search records").fill("it_student");
  await expect(page.getByText("it_student")).toBeVisible();
});

test("the roles page requires authentication (ADM-012-AC03)", async ({ page }) => {
  await page.goto("/it/admin/roles");
  await expect(page).toHaveURL(/\/it\/login/);
});
