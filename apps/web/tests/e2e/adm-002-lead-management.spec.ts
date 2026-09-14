import { test, expect } from "@playwright/test";

// ADM-002 -- CRM-linked enquiry/lead management. Requires the stack running via `docker
// compose up`. Submits its own throwaway enquiry via the real public API, then manages it
// as admin, rather than touching any shared seed data.

test("admin routes a lead to a new status, selected by name not a raw ID (ADM-002-AC01)", async ({ page, request }) => {
  const name = `E2E Lead ${Date.now()}`;
  const created = await request.post("/api/v1/public/enquiries", {
    data: { division: "it", name, email: `lead-${Date.now()}@example.com`, subject: "Python Full Stack", message: "Interested in the programme." },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/leads");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage leads" }) });
  await panel.getByLabel("Search by name, email, or subject").fill(name);
  const row = panel.locator("tr", { hasText: name });
  await expect(row).toBeVisible();
  await row.getByLabel(`${name} status`).selectOption("contacted");
  await expect(row).toContainText("Lead updated.");
  await expect(row).toContainText("contacted");
});

test("lead management requires authentication", async ({ page }) => {
  await page.goto("/it/admin/leads");
  await expect(page).toHaveURL(/\/it\/login/);
});
