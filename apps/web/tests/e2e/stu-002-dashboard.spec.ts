import { test, expect } from "@playwright/test";

// STU-002 -- Student dashboard. Requires the stack running via `docker compose up`
// with `python -m app.seed` already applied.

async function loginAsSeededStudent(page: import("@playwright/test").Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
}

test("dashboard shows course progress, attendance, pending fee, applied jobs, and enrollments in one view (STU-002-AC01)", async ({ page }) => {
  await loginAsSeededStudent(page);
  for (const label of ["Course progress", "Attendance", "Pending fee", "Applied jobs", "Enrollments"]) {
    await expect(page.locator(".metric", { hasText: label })).toBeVisible();
  }
});

test("dashboard shows upcoming assignments", async ({ page }) => {
  await loginAsSeededStudent(page);
  await expect(page.locator(".workspace-head", { hasText: "Student Dashboard" })).toBeVisible();
  await expect(page.locator("table")).toContainText("Python Full Stack Assignment");
});

test("dashboard requires authentication", async ({ page }) => {
  await page.goto("/it/student/dashboard");
  await expect(page).toHaveURL(/\/it\/login/);
});

test("dashboard is usable at a 375px viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await loginAsSeededStudent(page);
  await expect(page.getByText("Course progress", { exact: true })).toBeVisible();
});
