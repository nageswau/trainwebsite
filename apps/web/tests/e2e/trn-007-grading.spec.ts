import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// TRN-007 -- Submission review and grading. Requires the stack running via `docker
// compose up` with `python -m app.seed` already applied (seeds the demo trainer's batch
// and the demo student's enrolment in it).
//
// Creates its own uniquely-titled assignment and submits/grades that specific one, rather
// than grabbing "whatever's currently pending" for the shared demo student -- other specs
// (STU-004, TRN-005) also create and submit assignments for the same demo student and can
// run concurrently in a different worker, so picking "the first pending item" would race.

async function loginAs(page: Page, email: string, password: string, dashboardPath: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${dashboardPath}`);
}

async function accessCookie(page: Page) {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === "edusphere_access")?.value;
}

async function createAssignmentAsTrainer(page: Page, request: APIRequestContext, title: string) {
  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  const trainerAccess = await accessCookie(page);
  const trainerContext = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${trainerAccess}` } });
  const batchId = (await trainerContext.json()).batches[0]?.id;
  const created = await request.post("/api/v1/workflows/it/trainer/assignments", {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: {
      batch_id: batchId,
      title,
      description: "TRN-007 grading test assignment.",
      due_date: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
      max_score: 100,
      assignment_type: "assignment",
      submission_type: "text_or_file",
      published: true,
    },
  });
  expect(created.ok()).toBeTruthy();
}

test("trainer grades a submission by student name, and the student sees the result (TRN-007-AC01)", async ({ page, request }) => {
  const title = `TRN-007 Gradeable Assignment ${Date.now()}`;
  await createAssignmentAsTrainer(page, request, title);

  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  const studentAccess = await accessCookie(page);
  const portal = await request.get("/api/v1/portal/it/student/assignments", { headers: { cookie: `edusphere_access=${studentAccess}` } });
  const mine = (await portal.json()).rows.find((r: { title: string }) => r.title === title);
  const submitted = await request.post(`/api/v1/workflows/it/assignments/${mine.id}/submissions`, {
    headers: { cookie: `edusphere_access=${studentAccess}` },
    data: { answer: "TRN-007 grading test answer." },
  });
  expect(submitted.ok()).toBeTruthy();
  const submissionId = (await submitted.json()).id;

  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  await page.goto("/it/trainer/assignments");
  await page.getByLabel("Submitted work").selectOption(submissionId);
  await page.locator("#grade-score").fill("92");
  await page.locator("#grade-outcome").selectOption("graded");
  await page.locator("#grade-feedback").fill("Well done.");
  await page.getByRole("button", { name: "Publish grade" }).click();
  await expect(page.getByText("Submission graded.")).toBeVisible();

  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  const recheckAccess = await accessCookie(page);
  const recheck = await request.get("/api/v1/portal/it/student/assignments", { headers: { cookie: `edusphere_access=${recheckAccess}` } });
  const graded = (await recheck.json()).rows.find((r: { id: string }) => r.id === mine.id);
  expect(graded.score).toBe("92/100");
  expect(graded.feedback).toBe("Well done.");
});

test("grading requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/assignments");
  await expect(page).toHaveURL(/\/it\/login/);
});
