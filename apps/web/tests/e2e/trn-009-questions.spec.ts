import { test, expect } from "@playwright/test";

// TRN-009 -- Q&A response. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied (seeds the demo student's enrolment in the
// trainer's shared IT batch).

test("student asks a question and the trainer's reply appears for the student (TRN-009-AC01)", async ({ page }) => {
  const subject = `TRN-009 E2E Question ${Date.now()}`;

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/questions");
  const askCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "My Questions" }) });
  await askCard.getByLabel("Subject").fill(subject);
  await askCard.getByLabel("Question").fill("Could you clarify the grading rubric?");
  await askCard.getByRole("button", { name: "Ask question" }).click();
  await expect(askCard.getByText("Question submitted.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.goto("/it/trainer/questions");
  const replyCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Reply to question" }) });
  const threadSelect = replyCard.getByLabel("Question");
  const optionValue = await threadSelect.locator("option", { hasText: subject }).getAttribute("value");
  await threadSelect.selectOption(optionValue!);
  await replyCard.getByLabel("Reply").fill("Full rubric is in the course materials.");
  await replyCard.getByRole("button", { name: "Post reply" }).click();
  await expect(page.getByText("Reply posted.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/questions");
  // The shared seeded demo student accumulates one question thread per E2E run (same
  // pattern as RAID I-03) -- scope to this run's own uniquely-subjected thread card.
  const threadCard = page.locator(".card", { has: page.getByRole("heading", { name: subject }) });
  await expect(threadCard.getByText("Full rubric is in the course materials.")).toBeVisible();
});

test("question raising requires authentication", async ({ page }) => {
  await page.goto("/it/student/questions");
  await expect(page).toHaveURL(/\/it\/login/);
});
