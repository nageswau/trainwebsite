import { test, expect } from "@playwright/test";

// ADM-014 -- Super Admin cross-division console. The console pages themselves already
// existed (apps/web/app/admin/[module]/page.tsx + SUPER_ADMIN_NAV); the real gap this
// feature closed was the missing "security-log export" privileged action named in its
// own AC02. Confirms the real Super Admin can trigger it through the actual UI action
// and get a working download link, and that a non-Super-Admin is denied at the API layer.

test("Super Admin exports the audit log through the real UI action and gets a download link (ADM-014-AC01/AC02)", async ({ page }) => {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");

  await page.goto("/admin/security-logs");
  await expect(page.getByRole("heading", { name: "Export audit log" })).toBeVisible();
  await page.click("button:has-text('Export audit log')");
  await expect(page.getByText(/Export ready/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Download it here" })).toBeVisible();
});

test("a non-Super-Admin is denied the audit export at the API layer (ADM-014-AC03)", async ({ page }) => {
  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const response = await page.request.post("/api/v1/admin/audit/export");
  expect(response.status()).toBe(403);
});

test("the security-logs console requires authentication", async ({ page }) => {
  await page.goto("/admin/security-logs");
  await expect(page).toHaveURL(/\/admin\/login/);
});
