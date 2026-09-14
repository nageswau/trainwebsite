import { test, expect } from "@playwright/test";

// STU-009 -- Digital agreement / consent. A freshly booked slot locks its seat
// immediately (DEC-WF-002) but the enrolment itself stays "pending_consent" -- not
// visible anywhere as an active participant -- until the student reviews and accepts
// the current agreement.

async function registerStudent(page: import("@playwright/test").Page, email: string) {
  await page.goto("/it/register");
  await page.fill('input[name="full_name"]', "Consent Test Student");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/it/student/dashboard");
}

test("a newly booked slot requires reviewing and accepting the agreement before it activates (STU-009-AC01)", async ({ page }) => {
  const email = `stu009-accept-${Date.now()}@example.com`;
  await registerStudent(page, email);

  await page.goto("/it/student/course");
  await page.getByRole("button", { name: "Book this slot" }).first().click();
  await expect(page.getByText(/Enrolment confirmed/)).toBeVisible();

  await expect(page.getByRole("heading", { name: "Review and accept your enrolment agreement" })).toBeVisible();
  await expect(page.getByText(/Terms|agreement|policies|consent/i).first()).toBeVisible();

  await page.getByRole("button", { name: "I have read and accept this agreement" }).click();
  await expect(page.getByRole("heading", { name: "Review and accept your enrolment agreement" })).toHaveCount(0);
});

test("enrolment cannot complete without acceptance -- the seat is locked but not yet active (STU-009-AC02)", async ({ page, request }) => {
  const email = `stu009-pending-${Date.now()}@example.com`;
  await registerStudent(page, email);

  await page.goto("/it/student/course");
  await page.getByRole("button", { name: "Book this slot" }).first().click();
  await expect(page.getByText(/Enrolment confirmed/)).toBeVisible();

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
