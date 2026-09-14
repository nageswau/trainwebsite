import { test, expect } from "@playwright/test";

// AGT-001 -- Agent self-registration and approval gate. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds an
// `overseas_admin` account). Registers its own throwaway Agent account per test.

test("a newly self-registered agent sees a pending-approval message, not their dashboard (AGT-001-AC02)", async ({ page }) => {
  await page.goto("/overseas/register");
  const unique = Date.now();
  await page.fill('input[name="full_name"]', "E2E Agent");
  await page.fill('input[name="email"]', `agt001-e2e-${unique}@example.local`);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText(/pending approval/)).toBeVisible();
});

test("overseas admin approves a pending agent, who then reaches their dashboard (AGT-001-AC01)", async ({ page }) => {
  const unique = Date.now();
  const email = `agt001-e2e-${unique}@example.local`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: "E2E Agent", division: "overseas", account_type: "agent" },
  });
  expect(registered.ok()).toBeTruthy();

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/agents");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Agent Approvals" }) }).locator(".card", { hasText: "E2E Agent" }).filter({ hasText: email });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Approve" }).click();
  // The card moves from "Pending" into the "Decided" list -- it isn't removed, its own
  // badge just changes.
  await expect(card.getByText("approved")).toBeVisible();

  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).not.toBeVisible();
});
