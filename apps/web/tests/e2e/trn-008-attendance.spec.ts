import { test, expect } from "@playwright/test";

// TRN-008 -- Attendance marking. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied (seeds the demo trainer's batch with the demo
// student enrolled).

test("trainer marks attendance by student name, and the student sees it (TRN-008-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.goto("/it/trainer/attendance");
  const form = page.getByRole("form", { name: "Mark attendance" });
  await form.getByLabel("Batch").selectOption({ index: 1 });
  await expect(form.getByText("Arjun Rao")).toBeVisible();
  await form.getByLabel("Arjun Rao status").selectOption("present");
  await form.getByRole("button", { name: "Save attendance" }).click();
  await expect(page.getByText("Attendance saved.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
  await page.goto("/it/student/attendance");
  await expect(page.locator("table")).toContainText("present");
});

test("attendance marking requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/attendance");
  await expect(page).toHaveURL(/\/it\/login/);
});
