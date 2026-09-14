import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// STU-004 -- Assignment submission. Uses the seeded demo student (permanently enrolled in
// the idempotently-seeded "PY-FS-AUG-2026" batch, apps/api/app/seed.py), so repeated runs
// never consume shared, fixed-capacity enrolment slots. Each run creates its own uniquely
// titled assignment via the trainer API (mirroring the trainer's eventual assignment-
// creation flow, TRN-005's own scope), so a run never collides with a previous run's
// already-submitted assignment either.

async function loginAsSeededStudent(page: Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
}

async function createAssignmentAsTrainer(page: Page, request: APIRequestContext, title: string, dueDate: Date) {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");
  const trainerCookies = await page.context().cookies();
  const trainerAccess = trainerCookies.find((c) => c.name === "edusphere_access")?.value;
  const trainerContext = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${trainerAccess}` } });
  const batchId = (await trainerContext.json()).batches[0]?.id;
  const created = await request.post("/api/v1/workflows/it/trainer/assignments", {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: {
      batch_id: batchId,
      title,
      description: "E2E test assignment.",
      due_date: dueDate.toISOString(),
      max_score: 100,
      assignment_type: "assignment",
      submission_type: "text_or_file",
      published: true,
    },
  });
  expect(created.ok()).toBeTruthy();
}

test("student sees pending work with no manual reference typing, and can submit it (STU-004-AC01)", async ({ page, request }) => {
  const title = `On-Time E2E Assignment ${Date.now()}`;
  await createAssignmentAsTrainer(page, request, title, new Date(Date.now() + 5 * 24 * 60 * 60 * 1000));

  await loginAsSeededStudent(page);
  await page.goto("/it/student/assignments");
  await expect(page.getByRole("heading", { name: "Submit work" })).toBeVisible();
  await expect(page.getByLabel("Assignment reference")).toHaveCount(0);

  const card = page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });
  await card.getByRole("button", { name: "Submit this work" }).click();
  await card.locator("textarea[name='answer']").fill("My completed answer.");
  await card.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(card.getByText("Submitted on time.")).toBeVisible();
});

test("a late submission is flagged, not silently accepted as on-time (STU-004-AC02)", async ({ page, request }) => {
  const title = `Overdue E2E Assignment ${Date.now()}`;
  await createAssignmentAsTrainer(page, request, title, new Date(Date.now() - 2 * 24 * 60 * 60 * 1000));

  await loginAsSeededStudent(page);
  await page.goto("/it/student/assignments");
  const card = page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });
  await card.getByRole("button", { name: "Submit this work" }).click();
  await card.locator("textarea[name='answer']").fill("Late answer.");
  await card.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(card.getByText(/marked late/)).toBeVisible();
});

test("assignment submission requires authentication", async ({ page }) => {
  await page.goto("/it/student/assignments");
  await expect(page).toHaveURL(/\/it\/login/);
});
