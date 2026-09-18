import { test, expect } from "@playwright/test";

// STU-001 -- Trainer/batch slot enrolment. Creates its own throwaway program/batch via
// the real admin API (same pattern as adm-005-enrollment-review.spec.ts) rather than
// booking into a shared seeded batch: the batch picker groups slots by program and
// collapses every group except the one currently selected in its Program filter
// (BatchSlotPicker.tsx), and a shared batch's fixed 20-seat capacity can also fill up
// over repeated runs. A fresh, uniquely-named program/batch is guaranteed to be the only
// entry in its group (auto-expanded) and to always have room.

async function createThrowawayBatch(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "itadmin@edusphere.local", password: "Demo@123", division: "it" } });
  const programTitle = `STU-001 E2E Program ${Date.now()}`;
  const program = await page.request.post("/api/v1/admin/programs", {
    data: { slug: `stu-001-e2e-${Date.now()}`, category: "Software Development", title: programTitle, duration: "8 weeks", fees: 5000 },
  });
  expect(program.ok()).toBeTruthy();
  const batchName = `STU-001 E2E Batch ${Date.now()}`;
  const batch = await page.request.post("/api/v1/admin/batches", {
    data: {
      program_id: (await program.json()).id,
      name: batchName,
      start_date: new Date().toISOString().slice(0, 10),
      end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
      schedule: "Mon-Fri 7pm",
      capacity: 20,
    },
  });
  expect(batch.ok()).toBeTruthy();
  return { programTitle, batchName };
}

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

async function openOwnBatchGroup(page: import("@playwright/test").Page, programTitle: string) {
  await page.goto("/it/student/course");
  await expect(page.getByRole("heading", { name: "Choose a trainer/time-slot" })).toBeVisible();
  await page.getByLabel("Program").selectOption({ label: programTitle });
}

test("a new student sees real capacity-aware slots, not a bare text field (STU-001-AC01)", async ({ page }) => {
  const { programTitle, batchName } = await createThrowawayBatch(page);
  await registerFreshStudent(page);
  await openOwnBatchGroup(page, programTitle);
  const row = page.locator("tr", { hasText: batchName });
  await expect(row.getByText(/\d+ of \d+/)).toBeVisible();
  // The old generic action would have been a bare "Available batch reference" text
  // input -- confirm it is gone for this section.
  await expect(page.getByLabel("Available batch reference")).toHaveCount(0);
});

test("booking a slot confirms with a real enrolment reference (STU-001-AC01)", async ({ page }) => {
  const { programTitle, batchName } = await createThrowawayBatch(page);
  await registerFreshStudent(page);
  await openOwnBatchGroup(page, programTitle);
  await page.locator("tr", { hasText: batchName }).getByRole("button", { name: "Book this slot" }).click();
  await expect(page.getByText(/Enrolment confirmed\. Your enrolment reference is/)).toBeVisible();
});

test("re-booking an already-locked slot is rejected, not silently accepted (STU-001-AC02)", async ({ page }) => {
  const { programTitle, batchName } = await createThrowawayBatch(page);
  await registerFreshStudent(page);
  await openOwnBatchGroup(page, programTitle);
  const bookButton = page.locator("tr", { hasText: batchName }).getByRole("button", { name: "Book this slot" });
  await bookButton.click();
  await expect(page.getByText(/Enrolment confirmed/)).toBeVisible();

  // Same button, same batch (the picker doesn't re-fetch mid-session) -- clicking it
  // again must surface the server's duplicate-enrolment rejection, not a second
  // "confirmed" message.
  await bookButton.click();
  await expect(page.getByText(/already enrolled/i)).toBeVisible();
});

test("the enrolment workflow requires authentication -- an unauthenticated visitor is redirected to login", async ({ page }) => {
  await page.goto("/it/student/course");
  await expect(page).toHaveURL(/\/it\/login/);
});
