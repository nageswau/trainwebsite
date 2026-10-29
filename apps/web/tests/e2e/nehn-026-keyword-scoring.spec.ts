import { expect, test, type Page } from "@playwright/test";

// nehn-026 -- keyword auto-scoring of written answers (DEC-SCOPE-333). Needs the stack with `python -m app.seed` applied; the demo
// student must be enrolled in the trainer's first batch. AC1 4 of 5 keywords -> full suggested marks; AC2 the trainer override;
// AC3 nothing the student receives carries the keywords; AC4 a question without keywords stays manual.
const BASE = "/api/v1/workflows/it/trainer/assessments";
const KEYWORDS = ["idempotent", "retry", "same result", "side effect|side-effect", "request"];

async function signIn(page: Page, email: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(url => !url.pathname.endsWith("/login"));
}

test("a trainer reviews a keyword-scored written answer and overrides it (nehn-026 AC1-AC4)", async ({ page }) => {
  const title = `nehn-026 E2E Keywords ${Date.now()}`;
  await signIn(page, "trainer@edusphere.local");
  const context = await (await page.request.get("/api/v1/workflows/it/trainer/context")).json();
  const created = await page.request.post(BASE, { data: { batch_id: context.batches[0].id, title, scheduled_at: "2026-10-01T10:00:00Z", status: "open" } });
  expect(created.status()).toBe(201);
  const assessmentId = (await created.json()).id;

  // the trainer types the keywords in the Add question form
  await page.goto("/it/trainer/assessments");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add question" }) });
  await card.getByLabel("Assessment", { exact: true }).selectOption(assessmentId);
  await card.getByLabel("Question type").selectOption("text");
  await card.getByLabel("Question", { exact: true }).fill("Explain API idempotency.");
  await card.getByLabel("Keywords (written answers only), comma separated").fill(KEYWORDS.join(", "));
  await card.getByLabel("Score", { exact: true }).fill("10");
  await card.getByRole("button", { name: "Add question" }).click();
  await expect(page.getByText("Question added.")).toBeVisible();
  const second = await page.request.post(`${BASE}/${assessmentId}/questions`, { data: { question_type: "text", prompt: "Describe your week.", max_score: 5, position: 2 } });
  expect(second.status()).toBe(201);
  const questions = await (await page.request.get(`${BASE}/${assessmentId}/questions`)).json();
  expect(questions.map((q: { keywords: string[] }) => q.keywords)).toEqual([KEYWORDS, []]);

  // the student answers; nothing they receive carries the keywords (AC3)
  await signIn(page, "student.it@edusphere.local");
  const started = await page.request.post(`/api/v1/workflows/it/assessments/${assessmentId}/attempts`);
  expect(started.status()).toBe(201);
  const attempt = await started.json();
  const submitted = await page.request.post(`/api/v1/workflows/it/assessment-attempts/${attempt.id}/submit`, {
    data: { answers: [
      { question_id: questions[0].id, value: "An idempotent request is safe to retry and gives the same result every time." },
      { question_id: questions[1].id, value: "Busy" },
    ] },
  });
  expect(submitted.status()).toBe(200);
  expect((await submitted.json()).status).toBe("submitted");
  for (const text of [JSON.stringify(attempt), JSON.stringify(await submitted.json()), await (await page.request.get("/api/v1/workflows/it/student/learning")).text(), await (await page.request.get("/api/v1/portal/it/student/examinations")).text()]) {
    expect(text).not.toContain("side effect");
    expect(text).not.toContain("keywords");
  }

  // the trainer sees the suggestion (AC1), the manual question (AC4), and overrides (AC2)
  await signIn(page, "trainer@edusphere.local");
  await page.goto("/it/trainer/assessments");
  const grading = page.locator(".action-card", { has: page.getByRole("heading", { name: "Grade written attempt" }) });
  await grading.getByLabel("Submitted attempt").selectOption(attempt.id);
  const keywordItem = grading.locator(".qa-item", { hasText: "Explain API idempotency." });
  await expect(keywordItem.getByText("Keyword score · 10/10 · 80% matched")).toBeVisible();
  await expect(keywordItem.getByText("Matched: idempotent, retry, same result, request")).toBeVisible();
  await expect(keywordItem.getByText("Missing: side effect|side-effect")).toBeVisible();
  await expect(keywordItem.getByLabel("Score (of 10)")).toHaveValue("10");
  const plainItem = grading.locator(".qa-item", { hasText: "Describe your week." });
  await expect(plainItem.getByText("Max 5")).toBeVisible();
  await keywordItem.getByLabel("Score (of 10)").fill("7");
  await plainItem.getByLabel("Score (of 5)").fill("4");
  await grading.getByRole("button", { name: "Publish grade" }).click();
  await expect(page.getByText("Attempt graded.")).toBeVisible();

  await grading.getByLabel("Submitted attempt").selectOption(attempt.id);
  await expect(keywordItem.getByText("Trainer score · keyword suggestion 10/10 · 80% matched")).toBeVisible();
  await expect(keywordItem.getByLabel("Score (of 10)")).toHaveValue("7");
});
