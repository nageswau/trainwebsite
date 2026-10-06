import { test, expect } from "@playwright/test";

// ADM-002 -- CRM-linked enquiry/lead management. Requires the stack running via `docker
// compose up`. Submits its own throwaway enquiry via the real public API, then manages it
// as admin, rather than touching any shared seed data.

test("admin routes a lead to a new status, selected by name not a raw ID (ADM-002-AC01)", async ({ page, request }) => {
  test.setTimeout(30_000); // a sign-in plus several writes: 15 s ran out with 6 parallel workers on one API (tel-007 browser QA)
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
  await panel.getByLabel("Search leads").fill(name); // tel-003: the API searches; Enter submits
  await panel.getByLabel("Search leads").press("Enter");
  const row = panel.locator("tr", { hasText: name });
  await expect(row).toBeVisible();
  // tel-004: the status editor is the pipeline's "Change stage" (valid moves only)
  await row.getByRole("button", { name: `Change stage for ${name}` }).click();
  await row.getByLabel(`New stage for ${name}`).selectOption("qualified");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(row).toContainText("Stage updated.");
  await expect(row).toContainText("Qualified");
});

test("lead management requires authentication", async ({ page }) => {
  await page.goto("/it/admin/leads");
  await expect(page).toHaveURL(/\/it\/login/);
});
