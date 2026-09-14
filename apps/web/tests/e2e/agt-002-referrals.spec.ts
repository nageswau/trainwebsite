import { test, expect } from "@playwright/test";

// AGT-002 -- Referred-student roster and status. Uses the seeded demo agent
// (agent@edusphere.local), who has one referred student with one application already
// seeded (see `app/seed.py`). Confirms the roster shows the referral AND the student's
// current application status/university in one place -- the gap this feature fixed in
// `apps/api/app/services/portal.py`'s `_agent()` "students" branch.

test("agent's Students page shows each referred student's application status (AGT-002-AC01)", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");

  await page.goto("/overseas/agent/students");
  const row = page.locator("table tbody tr", { hasText: "Ananya Sharma" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("university_review");
  await expect(row).not.toContainText("No application yet");
});

test("a second, freshly self-registered agent with no referrals sees an empty roster, never the demo agent's (AGT-002-AC02)", async ({ page }) => {
  const unique = Date.now();
  const email = `agt002-e2e-${unique}@example.local`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: "E2E Second Agent", division: "overseas", account_type: "agent" },
  });
  expect(registered.ok()).toBeTruthy();

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Agent Approvals" }) }).locator(".card", { hasText: "E2E Second Agent" }).filter({ hasText: email });
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(card.getByText("approved")).toBeVisible();

  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");

  await page.goto("/overseas/agent/students");
  await expect(page.getByText("Ananya Sharma")).not.toBeVisible();
});
