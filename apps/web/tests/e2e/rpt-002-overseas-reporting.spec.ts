import { test, expect } from "@playwright/test";

// RPT-002 -- Overseas reporting. Tester feedback (2026-09-04, WhatsApp, RAID.md I-14):
// "ADMINISTRATOR: reports not working" -- the role was ambiguous, so every candidate
// Administrator was checked directly. IT Admin's and Placement Team's own Reports pages
// (RPT-001) already worked; Overseas Admin's own "Reports" nav link showed "Access
// unavailable -- Workspace not found" because RPT-002 (the feature that owns this
// role's own report) had never been built. Confirms it now renders real, data-derived
// content instead of 404ing.

test("Overseas Admin's Reports page loads with a real funnel, visa aging, and commission report instead of 404ing (RPT-002-AC01)", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/reports");
  await expect(page.getByRole("heading", { name: "Overseas Partner Reports" })).toBeVisible();
  await expect(page.getByText("Enquiry", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Agent commission report" })).toBeVisible();
});

test("a non-overseas-admin role cannot view this report at the API layer (RPT-002-AC03)", async ({ page }) => {
  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const response = await page.request.get("/api/v1/portal/overseas/admin/reports");
  expect(response.status()).toBe(403);
});

test("the overseas admin reports page requires authentication", async ({ page }) => {
  await page.goto("/overseas/admin/reports");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
