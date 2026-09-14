import { test, expect, type Page } from "@playwright/test";

// Fix for "no lock against adding a question after a student has started an attempt"
// (RAID.md I-18 sub-item 3). Confirms the real fix end to end: the "Add question"
// picker disables an assessment once it has attempt data, and the server rejects a
// direct API attempt to add a question to it regardless (defense in depth -- the picker
// being disabled must not be the only thing standing in the way).
//
// Creates its own uniquely-titled assessment via API, same "own throwaway record"
// convention as this suite's other specs.

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

test("a question can no longer be added once a student has started an attempt", async ({ page, request }) => {
  const title = `Question Lock E2E Quiz ${Date.now()}`;

  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  const trainerAccess = await accessCookie(page);
  const trainerContext = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${trainerAccess}` } });
  const batchId = (await trainerContext.json()).batches[0]?.id;

  const created = await request.post("/api/v1/workflows/it/trainer/assessments", {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { batch_id: batchId, title, scheduled_at: "2027-07-01T10:00:00Z", status: "scheduled" },
  });
  expect(created.ok()).toBeTruthy();
  const assessmentId = (await created.json()).id;

  const firstQuestion = await request.post(`/api/v1/workflows/it/trainer/assessments/${assessmentId}/questions`, {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { question_type: "text", prompt: "Original question.", max_score: 5, position: 1 },
  });
  expect(firstQuestion.ok()).toBeTruthy();

  await page.goto("/it/trainer/assessments");
  const addQuestionCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add question" }) });
  const assessmentOption = addQuestionCard.locator("select[name='assessment'] option", { hasText: title });
  await expect(assessmentOption).toBeEnabled(); // not locked yet -- no attempt exists

  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  const studentAccess = await accessCookie(page);
  const attempt = await request.post(`/api/v1/workflows/it/assessments/${assessmentId}/attempts`, { headers: { cookie: `edusphere_access=${studentAccess}` } });
  expect(attempt.ok()).toBeTruthy();

  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  await page.goto("/it/trainer/assessments");
  const lockedOption = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add question" }) }).locator("select[name='assessment'] option", { hasText: title });
  await expect(lockedOption).toBeDisabled(); // now locked -- the UI reflects the real attempt

  // Defense in depth: the server rejects it even bypassing the disabled UI control.
  const freshTrainerAccess = await accessCookie(page);
  const blocked = await request.post(`/api/v1/workflows/it/trainer/assessments/${assessmentId}/questions`, {
    headers: { cookie: `edusphere_access=${freshTrainerAccess}` },
    data: { question_type: "text", prompt: "Sneaked in after the student started.", max_score: 5, position: 2 },
  });
  expect(blocked.status()).toBe(409);
});
