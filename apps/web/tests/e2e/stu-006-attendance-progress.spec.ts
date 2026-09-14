import { test, expect } from "@playwright/test";

// STU-006 -- Attendance and progress view (PRD-STU-006 + PRD-STU-007). The bare
// attendance list and RBAC already had E2E coverage via TRN-008's spec; this covers
// the feature's own addition -- course/module completion % and outstanding blockers
// (unfinished assignments) surfaced on the same read-only page. Requires the stack
// running via `docker compose up` with `python -m app.seed` already applied (seeds
// the demo student's enrolment at 42% progress and 12 attendance records).

test("student sees course progress and outstanding blockers alongside attendance (STU-006-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/attendance");
  const progressMetric = page.locator(".metric", { hasText: "Course progress" });
  await expect(progressMetric.locator("strong")).toHaveText("42%");

  const attendanceMetric = page.locator(".metric", { hasText: "Attendance" }).first();
  await expect(attendanceMetric.locator("strong")).toHaveText(/^\d+%$/);

  await expect(page.locator(".panel", { hasText: "Outstanding blockers" })).toBeVisible();
});
