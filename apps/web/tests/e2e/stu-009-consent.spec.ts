import { test, expect } from "@playwright/test";

// STU-009 -- Digital agreement / consent. A freshly booked slot locks its seat
// immediately (DEC-WF-002) but the enrolment itself stays "pending_consent" -- not
// visible anywhere as an active participant -- until the student reviews and accepts
// the current agreement. Creates its own throwaway program/batch via the real admin API
// (same pattern as adm-005-enrollment-review.spec.ts / stu-001-enrollment.spec.ts) so a
// fresh student always has exactly one, guaranteed-open slot -- the batch picker groups
// slots by program and collapses every group except the one currently selected in its
// Program filter (BatchSlotPicker.tsx).

async function createThrowawayBatch(page: import("@playwright/test").Page, label: string) {
  await page.request.post("/api/v1/auth/login", { data: { email: "itadmin@edusphere.local", password: "Demo@123", division: "it" } });
  const programTitle = `STU-009 ${label} Program ${Date.now()}`;
  const program = await page.request.post("/api/v1/admin/programs", {
    data: { slug: `stu-009-${label.toLowerCase()}-${Date.now()}`, category: "Software Development", title: programTitle, duration: "8 weeks", fees: 5000 },
  });
  expect(program.ok()).toBeTruthy();
  const batchName = `STU-009 ${label} Batch ${Date.now()}`;
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

async function registerStudent(page: import("@playwright/test").Page, email: string) {
  await page.goto("/it/register");
  await page.fill('input[name="full_name"]', "Consent Test Student");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/it/student/dashboard");
}

async function bookOwnBatch(page: import("@playwright/test").Page, programTitle: string, batchName: string) {
  await page.goto("/it/student/course");
  await page.getByLabel("Program").selectOption({ label: programTitle });
  await page.locator("tr", { hasText: batchName }).getByRole("button", { name: "Book this slot" }).click();
  await expect(page.getByText(/Enrolment confirmed/)).toBeVisible();
}

test("a newly booked slot requires reviewing and accepting the agreement before it activates (STU-009-AC01)", async ({ page }) => {
  const { programTitle, batchName } = await createThrowawayBatch(page, "Accept");
  const email = `stu009-accept-${Date.now()}@example.com`;
  await registerStudent(page, email);
  await bookOwnBatch(page, programTitle, batchName);

  await expect(page.getByRole("heading", { name: "Review and accept your enrolment agreement" })).toBeVisible();
  await expect(page.getByText(/Terms|agreement|policies|consent/i).first()).toBeVisible();

  await page.getByRole("button", { name: "I have read and accept this agreement" }).click();
  await expect(page.getByRole("heading", { name: "Review and accept your enrolment agreement" })).toHaveCount(0);
});

test("enrolment cannot complete without acceptance -- the seat is locked but not yet active (STU-009-AC02)", async ({ page, request }) => {
  const { programTitle, batchName } = await createThrowawayBatch(page, "Pending");
  const email = `stu009-pending-${Date.now()}@example.com`;
  await registerStudent(page, email);
  await bookOwnBatch(page, programTitle, batchName);

  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access")?.value;
  const current = await request.get("/api/v1/workflows/it/student/agreements/current", { headers: { cookie: `edusphere_access=${access}` } });
  expect(current.ok()).toBeTruthy();
  const data = await current.json();
  expect(data.accepted).toBe(false);
  expect(data.pending_enrollments).toBe(1);

  // Re-navigating (not just staying on the same client-side state) still shows the
  // gate -- it isn't a one-time client hint that silently lets the student through.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Review and accept your enrolment agreement" })).toBeVisible();
});

test("the agreement acceptance workflow requires authentication", async ({ page, request }) => {
  await page.goto("/it/student/course");
  await expect(page).toHaveURL(/\/it\/login/);

  const response = await request.get("/api/v1/workflows/it/student/agreements/current");
  expect(response.status()).toBe(401);
});
