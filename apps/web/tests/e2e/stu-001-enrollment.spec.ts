import { test, expect } from "@playwright/test";

// STU-001 -- Trainer/batch slot enrolment. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeded batches exist).

async function registerFreshStudent(page: import("@playwright/test").Page) {
  const email = `stu001-${Date.now()}@example.com`;
  await page.goto("/it/register");
  await page.fill('input[name="full_name"]', "Fresh Enrolment Student");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/it/student/dashboard");
  return email;
}

test("a new student sees real capacity-aware slots, not a bare text field (STU-001-AC01)", async ({ page }) => {
  await registerFreshStudent(page);
  await page.goto("/it/student/course");
  await expect(page.getByRole("heading", { name: "Choose a trainer/time-slot" })).toBeVisible();
  await expect(page.getByText(/of \d+ slots available/).first()).toBeVisible();
  // The old generic action would have been a bare "Available batch reference" text
  // input -- confirm it is gone for this section.
  await expect(page.getByLabel("Available batch reference")).toHaveCount(0);
});

test("booking a slot confirms with a real enrolment reference (STU-001-AC01)", async ({ page }) => {
  await registerFreshStudent(page);
  await page.goto("/it/student/course");
  await page.getByRole("button", { name: "Book this slot" }).first().click();
  await expect(page.getByText(/Enrolment confirmed\. Your enrolment reference is/)).toBeVisible();
});

test("re-booking an already-locked slot is rejected, not silently accepted (STU-001-AC02)", async ({ page }) => {
  await registerFreshStudent(page);
  await page.goto("/it/student/course");
  const firstSlot = page.getByRole("button", { name: "Book this slot" }).first();
  await firstSlot.click();
  await expect(page.getByText(/Enrolment confirmed/)).toBeVisible();

  // Same button, same batch (the picker doesn't re-fetch mid-session) -- clicking it
  // again must surface the server's duplicate-enrolment rejection, not a second
  // "confirmed" message.
  await firstSlot.click();
  await expect(page.getByText(/already enrolled/i)).toBeVisible();
});

test("the enrolment workflow requires authentication -- an unauthenticated visitor is redirected to login", async ({ page }) => {
  await page.goto("/it/student/course");
  await expect(page).toHaveURL(/\/it\/login/);
});
