import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// Fix for the "blind grading" bug (RAID.md, Trainer assessments page): the "Grade
// written attempt" card previously showed only a bare total-score input with no view of
// what the student actually wrote -- a trainer had to grade blind. This confirms the
// review pane now shows the student's real submitted answer per question before the
// trainer scores it.
//
// Creates its own uniquely-titled assessment (via API) and its own throwaway student
// attempt, rather than relying on the shared seeded assessment -- same "own throwaway
// record" convention TRN-007's own grading spec already established, since other specs
// can create/submit attempts against shared data concurrently.

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

test("trainer sees the student's real written answer before grading, not a blind score field", async ({ page, request }) => {
  const title = `Grading Review Quiz ${Date.now()}`;
  const writtenAnswer = `Playwright E2E answer ${Date.now()}: dependency injection resolves per-request.`;

  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  const trainerAccess = await accessCookie(page);
  const trainerContext = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${trainerAccess}` } });
  const batchId = (await trainerContext.json()).batches[0]?.id;

  const created = await request.post("/api/v1/workflows/it/trainer/assessments", {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { batch_id: batchId, title, scheduled_at: "2027-03-01T10:00:00Z", status: "open" },
  });
  expect(created.ok()).toBeTruthy();
  const assessmentId = (await created.json()).id;

  const mcq = await request.post(`/api/v1/workflows/it/trainer/assessments/${assessmentId}/questions`, {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { question_type: "mcq_single", prompt: "1 + 1 = ?", options: ["1", "2", "3"], correct_answers: ["2"], max_score: 5, position: 1 },
  });
  expect(mcq.ok()).toBeTruthy();
  const written = await request.post(`/api/v1/workflows/it/trainer/assessments/${assessmentId}/questions`, {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { question_type: "text", prompt: "Explain dependency injection.", max_score: 5, position: 2 },
  });
  expect(written.ok()).toBeTruthy();

  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  const studentAccess = await accessCookie(page);
  const attempt = await request.post(`/api/v1/workflows/it/assessments/${assessmentId}/attempts`, { headers: { cookie: `edusphere_access=${studentAccess}` } });
  expect(attempt.ok()).toBeTruthy();
  const attemptId = (await attempt.json()).id;
  const submit = await request.post(`/api/v1/workflows/it/assessment-attempts/${attemptId}/submit`, {
    headers: { cookie: `edusphere_access=${studentAccess}` },
    data: { answers: [
      { question_id: (await mcq.json()).id, value: "2" },
      { question_id: (await written.json()).id, value: writtenAnswer },
    ] },
  });
  expect(submit.ok()).toBeTruthy();

  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  await page.goto("/it/trainer/assessments");
  const gradeCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Grade written attempt" }) });
  await gradeCard.getByLabel("Submitted attempt").selectOption({ label: `Arjun Rao · ${title} · submitted` });

  // The real submitted answer must actually be visible before any score is entered --
  // this is the defect itself: it previously never rendered anywhere.
  await expect(gradeCard.getByText(writtenAnswer)).toBeVisible();
  await expect(gradeCard.getByText("Auto-graded")).toBeVisible();

  await gradeCard.getByLabel(/Score \(of 5\)/).fill("4");
  await gradeCard.getByLabel("Feedback").fill("Good, minor gap on scoping.");
  await gradeCard.getByRole("button", { name: "Publish grade" }).click();
  await expect(page.getByText("Attempt graded.")).toBeVisible();

  const recheck = await request.get("/api/v1/workflows/it/trainer/assessment-attempts", { headers: { cookie: `edusphere_access=${trainerAccess}` } });
  const graded = (await recheck.json()).find((a: { assessment: string }) => a.assessment === title);
  expect(graded.status).toBe("graded");
  expect(graded.score).toBe(9); // 5 (auto MCQ) + 4 (manually scored written answer)
});

test("grade attempt view requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/assessments");
  await expect(page).toHaveURL(/\/it\/login/);
});
