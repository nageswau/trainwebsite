import { test, expect, type Page } from "@playwright/test";

// nehn-033 (DEC-SCOPE-332) -- the overseas student's Progress page: a stepper per application, the documents still to upload (each
// linking to upload) and the next actions. Requires the seeded stack: the demo student's application is at the legacy
// `university_review` status ("Offer processing") with a visa case whose checklist lacks Offer letter, Financial evidence and Visa form.

async function login(page: Page, email: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
}

test("the demo student reads their stage, missing documents and next actions on one page", async ({ page }) => {
  await login(page, "student.overseas@edusphere.local");
  await page.waitForURL("**/overseas/student/dashboard");
  await page.getByRole("link", { name: "Progress", exact: true }).click();
  await expect(page).toHaveURL(/\/overseas\/student\/progress$/);
  await expect(page.getByRole("heading", { name: "Progress", exact: true })).toBeVisible();

  const steps = page.getByRole("list", { name: /^Progress of / }).first();
  await expect(steps.getByRole("listitem")).toHaveCount(9);
  await expect(steps.locator('[aria-current="step"]')).toContainText("Offer processing");
  await expect(steps.locator('[aria-current="step"]')).toContainText("Current");
  await expect(steps.getByRole("listitem").first()).toContainText("Done");

  const missing = page.getByRole("list", { name: "Missing documents" });
  await expect(missing.getByRole("listitem").filter({ hasText: "Visa form" })).toContainText("Visa checklist");
  await expect(missing.getByRole("listitem").filter({ hasText: "Statement of Purpose" })).toHaveCount(0); // uploaded, awaiting review

  await expect(page.getByRole("list", { name: "Next actions" })).toContainText("Await the university admission decision");
  await missing.getByRole("link", { name: "Upload Visa form" }).click();
  await expect(page).toHaveURL(/\/overseas\/student\/documents$/);
});

test("a counselor cannot open the student's Progress page", async ({ page }) => {
  await login(page, "counselor@edusphere.local");
  await page.waitForURL("**/overseas/counselor/**");
  await page.goto("/overseas/student/progress");
  await expect(page.getByRole("list", { name: /^Progress of / })).toHaveCount(0);
});
