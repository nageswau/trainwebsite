import { test, expect } from "@playwright/test";

// ENH-001 -- Academic-Year foundation model, frontend slice: `grade_level` field on the
// coordinator's student create/edit forms (SchoolStudentsPanel.tsx). Requires the stack
// running via `docker compose up` with `python -m app.seed` already applied (seeds an
// `overseas_admin` account, overseasadmin@edusphere.local/Demo@123).
//
// Review finding fix: this plan's own Task 8 deliberately skipped Playwright coverage in
// favor of a one-off manual browser check, with no artifact left in the repo proving it
// happened. This spec closes that gap with real, automated, repeatable coverage of the
// create -> persist -> reload -> edit -> persist -> reload round trip.

async function onboardSchoolWithCoordinator(page: import("@playwright/test").Page, unique: number) {
  const coordinatorEmail = `enh001-e2e-coord-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-001 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E ENH-001 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.click('button:has-text("Create school + seed Coordinator")');
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", "ChangeMe@12345");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  return { coordinatorEmail };
}

test("coordinator sets grade_level on create, it persists across reload, and edit updates it (ENH-001)", async ({ page }) => {
  const unique = Date.now();
  await onboardSchoolWithCoordinator(page, unique);

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "E2E Grade Level Student");
  await page.fill("#new-grade", "Grade 7");
  await page.fill("#new-grade-level", "7");
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();

  // Persists across a full reload, not just in the client's own post-submit state.
  await page.reload();
  const row = page.locator("tr", { hasText: "E2E Grade Level Student" });
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#edit-grade-level")).toHaveValue("7");

  // Editing it updates the stored value, and that update also survives a reload.
  await page.fill("#edit-grade-level", "8");
  await page.click('button:has-text("Save changes")');
  await expect(page.getByText(/Student updated\./)).toBeVisible();

  await page.reload();
  const rowAgain = page.locator("tr", { hasText: "E2E Grade Level Student" });
  await rowAgain.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#edit-grade-level")).toHaveValue("8");
});

test("the browser blocks an out-of-range grade_level before it ever reaches the server (ENH-001)", async ({ page }) => {
  const unique = Date.now();
  await onboardSchoolWithCoordinator(page, unique);

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "E2E Invalid Grade Level Student");
  await page.fill("#new-grade-level", "13");
  const isValid = await page.locator("#new-grade-level").evaluate((el: HTMLInputElement) => el.checkValidity());
  expect(isValid).toBe(false);
});
