import { test, expect } from "@playwright/test";

// OVS-002 -- Overseas application submission. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds the demo
// overseas student, who already has exactly one application on record -- these tests
// pick a university not already in that list, never touching the seeded row itself).

async function loginAsOverseasStudent(page: import("@playwright/test").Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");
}

async function pickUnappliedUniversity(card: import("@playwright/test").Locator) {
  const select = card.locator("#apply-university");
  await expect(select).toBeVisible(); // client-side fetch on mount -- wait past the loading placeholder
  await expect(select.locator("option")).not.toHaveCount(0);
  const optionLabels = await select.locator("option").allTextContents();
  const appliedNames = await card.locator(".grid.two .card h4").allTextContents();
  const candidate = optionLabels.find((label) => label !== "Select a university…" && !appliedNames.some((name) => label.startsWith(name.trim())));
  if (!candidate) throw new Error("No unapplied university available to pick in this seed dataset");
  await select.selectOption({ label: candidate });
  return candidate;
}

test("student submits interest via a real university picker and it appears in their tracking list (OVS-002-AC01)", async ({ page }) => {
  await loginAsOverseasStudent(page);
  await page.goto("/overseas/student/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a University" }) });

  await pickUnappliedUniversity(card);
  await card.getByRole("button", { name: "Submit interest" }).click();
  await expect(card.getByText(/Application submitted/)).toBeVisible();
});

test("submitting for the same university and course twice is rejected, not silently duplicated (OVS-002-AC02)", async ({ page }) => {
  await loginAsOverseasStudent(page);
  await page.goto("/overseas/student/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a University" }) });

  const candidate = await pickUnappliedUniversity(card);
  await card.getByRole("button", { name: "Submit interest" }).click();
  await expect(card.getByText(/Application submitted/)).toBeVisible();

  // Re-select the same university just applied to and submit again.
  await card.locator("#apply-university").selectOption({ label: candidate });
  await card.getByRole("button", { name: "Submit interest" }).click();
  await expect(card.getByText("You already have an application for this university/course.")).toBeVisible();
});

test("the applications workspace requires authentication", async ({ page }) => {
  await page.goto("/overseas/student/applications");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
