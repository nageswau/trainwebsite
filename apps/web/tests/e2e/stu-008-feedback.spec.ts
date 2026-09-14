import { test, expect } from "@playwright/test";

// STU-008 -- Feedback submission. Requires the stack running via `docker compose up`
// with `python -m app.seed` already applied (seeds the demo student's enrolment in the
// shared IT batch).

test("student submits feedback for an enrolled batch (STU-008-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/feedback");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Course Feedback" }) });
  const courseCard = card.locator(".card").first();
  await courseCard.getByRole("button", { name: /Give feedback|Submit feedback again/ }).click();
  await courseCard.getByLabel("Rating").selectOption("5");
  await courseCard.getByLabel("Comments").fill("Excellent trainer and pace.");
  await courseCard.getByRole("button", { name: "Submit feedback" }).click();
  await expect(courseCard.getByText("Feedback submitted -- thank you.")).toBeVisible();
});

test("feedback for a batch the student isn't enrolled in is rejected (STU-008-AC03)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  const response = await page.request.post("/api/v1/workflows/it/student/feedback", {
    data: { batch_id: "00000000-0000-0000-0000-000000000000", rating: 4 },
  });
  expect(response.status()).toBe(422);
});

test("feedback submission requires authentication", async ({ page }) => {
  await page.goto("/it/student/feedback");
  await expect(page).toHaveURL(/\/it\/login/);
});
