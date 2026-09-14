import { test, expect } from "@playwright/test";

// CNS-001 -- Counselor workspace [base]. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied. "Leads" and "Reports"
// previously 404'd ("Workspace not found") for every Counselor -- confirmed directly
// against the running stack before this fix.

async function loginAsCounselor(page: import("@playwright/test").Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");
}

test("counselor's Leads workspace loads instead of 404ing (CNS-001-AC01)", async ({ page }) => {
  await loginAsCounselor(page);
  await page.goto("/overseas/counselor/leads");
  await expect(page.getByRole("heading", { name: "My Leads", level: 2 })).toBeVisible();
});

test("counselor's Reports workspace loads with a real aggregate of their own caseload (CNS-001-AC01)", async ({ page }) => {
  await loginAsCounselor(page);
  await page.goto("/overseas/counselor/reports");
  await expect(page.getByRole("heading", { name: "My Caseload Report", level: 2 })).toBeVisible();
  await expect(page.getByText("Assigned applications", { exact: true })).toBeVisible();
});

test("counselor workspace sections require authentication", async ({ page }) => {
  await page.goto("/overseas/counselor/leads");
  await expect(page).toHaveURL(/\/overseas\/login/);
  await page.goto("/overseas/counselor/reports");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
