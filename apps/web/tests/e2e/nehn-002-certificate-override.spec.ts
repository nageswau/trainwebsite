import { test, expect } from "@playwright/test";

// nehn-002 -- the trainer's "Issue certificate" card: an override with a blank or whitespace-only reason is
// stopped in the browser (no request), and unticking the override hides the reason field again.
// Requires the stack running via `docker compose up` with `python -m app.seed` already applied.
test("trainer override with a whitespace-only reason shows a message and sends no request (nehn-002 AC2)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.goto("/it/trainer/student-progress");
  const issueCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Issue certificate" }) });
  await issueCard.getByLabel("Eligible learner").selectOption({ index: 1 });
  await issueCard.getByLabel("Override unmet criteria").check();
  await issueCard.getByLabel(/Override reason/).fill("    ");

  let issueRequests = 0;
  page.on("request", request => { if (request.method() === "POST" && /\/certificates\/[^/]+\/issue$/.test(request.url())) issueRequests += 1; });
  await issueCard.getByRole("button", { name: "Issue certificate" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Enter a reason for the override.");
  expect(issueRequests).toBe(0);

  await issueCard.getByLabel("Override unmet criteria").uncheck();
  await expect(issueCard.getByLabel(/Override reason/)).toHaveCount(0);
});
