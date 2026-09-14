import { test, expect } from "@playwright/test";

// RPT-001 -- Domestic/Employer reporting. Neither IT Admin's nor Placement Team's
// "Reports" nav link had a working handler before this feature -- both 404'd
// ("Workspace not found"), the same bug class CNS-001/UNI-001 found for their own
// roles. Confirms both now render real, data-derived content through the existing
// generic portal page (no new frontend code was needed, only the backend handler).

test("IT Admin's Reports page loads with a real funnel instead of 404ing (RPT-001-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/reports");
  await expect(page.getByRole("heading", { name: "IT Reports" })).toBeVisible();
  await expect(page.getByText("Enrolments", { exact: true })).toBeVisible();
  await expect(page.getByText("Certificates issued")).toBeVisible();
});

test("Placement Team's Reports page loads with real job activity instead of 404ing (RPT-001-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "placement@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/placement/dashboard");

  await page.goto("/it/placement/reports");
  await expect(page.getByRole("heading", { name: "Placement Reports" })).toBeVisible();
  await expect(page.getByText("Job requirements")).toBeVisible();
});

test("a non-admin role cannot view IT reports at the API layer (RPT-001-AC03)", async ({ page }) => {
  await page.request.post("/api/v1/auth/login", { data: { email: "student.it@edusphere.local", password: "Demo@123", division: "it" } });
  const response = await page.request.get("/api/v1/portal/it/admin/reports");
  expect(response.status()).toBe(403);
});

test("the IT admin reports page requires authentication", async ({ page }) => {
  await page.goto("/it/admin/reports");
  await expect(page).toHaveURL(/\/it\/login/);
});
