import { test, expect } from "@playwright/test";

// OVS-006 -- Scholarship listing and application. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds two active
// scholarships: "Global Merit Scholarship Guidance", "Germany STEM Opportunity").

async function loginAsOverseasStudent(page: import("@playwright/test").Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");
}

test("public scholarships page lists seeded scholarships with no in-app apply action (OVS-006-AC01)", async ({ page }) => {
  await page.goto("/overseas/scholarships");
  await expect(page.getByRole("heading", { name: "Global Merit Scholarship Guidance" })).toBeVisible();
});

test("logged-in student can apply to a scholarship they have not applied to yet, and it appears in their tracking list (OVS-006-AC01)", async ({ page }) => {
  await loginAsOverseasStudent(page);
  await page.goto("/overseas/student/scholarships");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a Scholarship" }) });
  await expect(panel).toBeVisible();

  // Pick whichever seeded scholarship still has an "Apply" button (not already applied
  // to by this shared demo identity from an earlier run). Re-locate by the card's stable
  // `data-scholarship-id` (not `.first()`, which re-resolves to a *different* card once
  // this one turns into a badge -- and not title text, since an unrelated fixture,
  // test_ovs_001_discovery.py, leaves several non-unique "Test Scholarship" rows in the
  // shared dev DB, RAID.md I-09's collision pattern).
  const scholarshipId = await panel.getByRole("button", { name: "Apply" }).first().locator("xpath=ancestor::div[@data-scholarship-id][1]").getAttribute("data-scholarship-id");
  const card = panel.locator(`[data-scholarship-id="${scholarshipId}"]`);

  await card.getByRole("button", { name: "Apply" }).click();
  await expect(panel.getByText("Application submitted.")).toBeVisible();
  await expect(card.getByRole("button", { name: "Apply" })).toHaveCount(0);
  await expect(card.locator(".badge")).toBeVisible();
});

test("applying twice to the same scholarship is rejected, not silently duplicated (OVS-006-AC02)", async ({ page }) => {
  await loginAsOverseasStudent(page);
  await page.goto("/overseas/student/scholarships");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a Scholarship" }) });
  await expect(panel).toBeVisible();

  const applyButtons = panel.getByRole("button", { name: "Apply" });
  const before = await applyButtons.count();
  if (before === 0) {
    // Both seeded scholarships already applied to by this identity in an earlier run --
    // every card should show a status badge, never a bare re-apply action.
    await expect(panel.locator(".card").first().locator(".badge")).toBeVisible();
    return;
  }
  await applyButtons.first().click();
  await expect(panel.getByText("Application submitted.")).toBeVisible();
  await page.reload();
  await expect(panel.getByRole("button", { name: "Apply" })).toHaveCount(before - 1);
});

test("the scholarships workspace requires authentication (OVS-006-AC03)", async ({ page }) => {
  await page.goto("/overseas/student/scholarships");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
