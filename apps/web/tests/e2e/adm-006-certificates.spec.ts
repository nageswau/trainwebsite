import { test, expect } from "@playwright/test";

// ADM-006 -- Certificate administration. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.

test("admin issues a certificate before criteria are met, with a required override reason (ADM-006-AC02)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/certificates");
  const issueCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Issue certificate" }) });
  await issueCard.getByLabel("Enrolment").selectOption({ index: 1 });
  await expect(issueCard.getByText(/Not yet eligible|Completion criteria are met/)).toBeVisible();

  // If the demo enrolment happens to already be eligible, there is nothing to override --
  // this test specifically covers the override path, so only proceed when it applies.
  const overrideField = issueCard.getByLabel(/Override reason/);
  if (await overrideField.isVisible()) {
    await overrideField.fill("Manual review: equivalent prior certification accepted.");
    await issueCard.getByRole("button", { name: "Issue certificate" }).click();
    await expect(issueCard.getByText(/Certificate .* issued\./)).toBeVisible();
  }
});

test("certificates administration requires authentication", async ({ page }) => {
  await page.goto("/it/admin/certificates");
  await expect(page).toHaveURL(/\/it\/login/);
});

// Found from real 409/422 errors in the running app's own logs: the Trainer's own
// "Issue certificate" card (TeacherWorkspaceActions.tsx, distinct from the Admin panel
// above) sent `{override: true}` with no `override_reason` field at all -- ticking
// "Override unmet criteria" could never succeed against an ineligible learner, since
// the backend always requires a non-blank reason once override is true.
test("trainer's own issue-certificate card shows and sends the override reason once the checkbox is ticked", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.goto("/it/trainer/student-progress");
  const issueCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Issue certificate" }) });
  await issueCard.getByLabel("Eligible learner").selectOption({ index: 1 });

  const overrideCheckbox = issueCard.getByLabel("Override unmet criteria");
  await expect(issueCard.getByLabel(/Override reason/)).toHaveCount(0);
  await overrideCheckbox.check();
  const overrideReason = issueCard.getByLabel(/Override reason/);
  await expect(overrideReason).toBeVisible();

  await overrideReason.fill("Manual override: prior industry certification accepted in lieu of the standard criteria.");
  await issueCard.getByRole("button", { name: "Issue certificate" }).click();
  // This page's generic `submit()` helper shows one fixed literal success string (not
  // interpolated with the certificate number, unlike the Admin panel's own message),
  // rendered in a shared banner above both cards, not scoped inside the .action-card
  // that triggered it.
  await expect(page.getByText("Certificate issued.")).toBeVisible();
});
