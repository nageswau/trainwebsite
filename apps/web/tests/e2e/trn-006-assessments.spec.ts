import { test, expect } from "@playwright/test";

// TRN-006 -- Assessment create and edit. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds the demo
// trainer's batch with the demo student enrolled).

test("trainer creates a draft assessment (hidden from students) then publishes it via edit (TRN-006-AC01/AC02)", async ({ page }) => {
  const title = `TRN-006 E2E Assessment ${Date.now()}`;

  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.goto("/it/trainer/assessments");
  const createCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Create assessment" }) });
  await createCard.getByLabel("Batch").selectOption({ index: 1 });
  await createCard.getByLabel("Title").fill(title);
  await createCard.getByLabel("Scheduled date and time").fill("2027-02-01T10:00");
  await createCard.getByLabel("Status").selectOption("draft");
  await createCard.getByRole("button", { name: "Create assessment" }).click();
  await expect(page.getByText("Assessment created.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/examinations");
  await expect(page.locator("table")).not.toContainText(title);

  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  const assessments = await (await page.request.get("/api/v1/workflows/it/trainer/assessments")).json();
  const assessmentId = assessments.find((a: { title: string }) => a.title === title)?.id;
  expect(assessmentId).toBeTruthy();

  await page.goto("/it/trainer/assessments");
  const editCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Edit assessment" }) });
  await editCard.getByLabel("Assessment").selectOption(assessmentId);
  await editCard.getByLabel("Status").selectOption("scheduled");
  await editCard.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Assessment updated.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/examinations");
  // The generic DataTable paginates client-side (10 rows/page) -- with enough
  // accumulated records this run's own row can land past page 1 and never appear in
  // `table` text at all despite being present in the full dataset. Search narrows the
  // table down to just this run's own row regardless of how many others exist.
  await page.getByLabel("Search records").fill(title);
  await expect(page.locator("table")).toContainText(title);
});

test("assessment editing requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/assessments");
  await expect(page).toHaveURL(/\/it\/login/);
});
