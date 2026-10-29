import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

// nehn-025 -- trainer question upload from the standard Excel template. Needs the stack with `python -m app.seed` applied.
// The fixture is the real downloaded template filled with 20 mixed questions (AC1); a CSV with `correct=7` covers AC2.
const FIXTURE = path.join(__dirname, "fixtures", "nehn-025-twenty-questions.xlsx");
const BASE = "/api/v1/workflows/it/trainer/assessments";

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(url => !url.pathname.endsWith("/login"));
}

test("a trainer imports the filled template into a draft that students cannot see (nehn-025 AC1, AC2, AC4)", async ({ page }) => {
  const title = `nehn-025 E2E Import ${Date.now()}`;
  await signIn(page, "trainer@edusphere.local");
  const context = await (await page.request.get("/api/v1/workflows/it/trainer/context")).json();
  const created = await page.request.post(BASE, { data: { batch_id: context.batches[0].id, title, scheduled_at: "2027-03-01T10:00:00Z", status: "draft" } });
  expect(created.status()).toBe(201);
  const assessmentId = (await created.json()).id;

  await page.goto("/it/trainer/assessments");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Import questions from Excel" }) });
  const download = page.waitForEvent("download");
  await card.getByRole("link", { name: "Download the question template" }).click();
  expect((await download).suggestedFilename()).toBe("question-template.xlsx");

  // AC2: a bad row is named and nothing can be imported
  await card.getByLabel("Assessment to fill").selectOption(assessmentId);
  const csv = "type,question,option_1,option_2,option_3,option_4,correct\nmcq_single,Fine one,a,b,,,1\nmcq_single,Bad one,a,b,c,d,7\n";
  await card.getByLabel("Filled template (.xlsx or .csv)").setInputFiles({ name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await card.getByRole("button", { name: "Check file" }).click();
  const errors = card.getByRole("table", { name: "Rows with errors" });
  await expect(errors).toContainText("3");
  await expect(errors).toContainText("Correct answer 7 is not a filled option (options 1-4 are filled)");
  await expect(card.getByRole("button", { name: /^Import \d+ question/ })).toHaveCount(0);

  // AC1: the filled template previews clean and imports every row
  await card.getByRole("button", { name: "Choose another file" }).click();
  await card.getByLabel("Filled template (.xlsx or .csv)").setInputFiles(FIXTURE);
  await card.getByRole("button", { name: "Check file" }).click();
  await expect(card.getByText(`20 questions are ready to import into ${title}.`)).toBeVisible();
  await expect(card.getByRole("table", { name: "Questions in the file" }).getByRole("row")).toHaveCount(21);
  await card.getByRole("button", { name: "Import 20 questions" }).click();
  await expect(card.locator(".form-message")).toHaveText(`20 questions imported into ${title}. A Draft stays hidden from students until you publish it in Edit assessment.`);

  const questions = await (await page.request.get(`${BASE}/${assessmentId}/questions`)).json();
  expect(questions).toHaveLength(20);
  const mine = (await (await page.request.get(BASE)).json()).find((a: { id: string }) => a.id === assessmentId);
  expect(mine.status).toBe("draft");

  // AC4: the student does not see the draft
  await signIn(page, "student.it@edusphere.local");
  const exams = await (await page.request.get("/api/v1/portal/it/student/examinations")).json();
  expect(exams.rows.map((row: { title: string }) => row.title)).not.toContain(title);
});
