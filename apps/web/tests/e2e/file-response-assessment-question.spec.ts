import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

// Fix for the "file-response questions unanswerable" bug (RAID.md I-18 sub-item 2): a
// `file`-response assessment question previously fell back to the same plain textarea
// used for a `text` question, since AssessmentForm only special-cased MCQ types --
// nothing was ever actually uploaded. Confirms the real fix: a genuine <input
// type="file"> renders for a `file` question, a real file uploaded through it reaches
// the trainer's grading review pane (the fix from RAID.md I-18 sub-item 1) as a working
// "Open submitted file" link, not empty/placeholder text.
//
// Creates its own uniquely-titled assessment via API (trainer setup only -- the actual
// file upload and submission happens through the real UI, since that's the code path
// under test), same "own throwaway record" convention as this suite's other specs.

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

test("student answers a file-response question with a real upload, and the trainer sees a working file link", async ({ page, request }) => {
  const title = `File Response E2E Quiz ${Date.now()}`;

  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  const trainerAccess = await accessCookie(page);
  const trainerContext = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${trainerAccess}` } });
  // The trainer now has more than one batch -- picking index 0 blindly is fragile
  // (whichever batch happens to sort first may not be the seeded demo student's own),
  // so pick the specific batch that student is actually enrolled in.
  const batches = (await trainerContext.json()).batches as { id: string; name: string }[];
  const batchId = (batches.find((b) => b.name === "PY-FS-AUG-2026") ?? batches[0])?.id;

  const created = await request.post("/api/v1/workflows/it/trainer/assessments", {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { batch_id: batchId, title, scheduled_at: "2027-05-01T10:00:00Z", status: "scheduled" },
  });
  expect(created.ok()).toBeTruthy();
  const assessmentId = (await created.json()).id;

  const question = await request.post(`/api/v1/workflows/it/trainer/assessments/${assessmentId}/questions`, {
    headers: { cookie: `edusphere_access=${trainerAccess}` },
    data: { question_type: "file", prompt: "Upload your worked-out solution.", max_score: 10, position: 1 },
  });
  expect(question.ok()).toBeTruthy();

  // Student side: start the attempt through the real UI and confirm a genuine file
  // input renders for this question -- not a textarea.
  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  await page.goto("/it/student/examinations");
  const takeCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Take assessment" }) });
  // RAID.md I-30: this used to be a raw UUID typed into a bare text input -- now a real
  // picker, selected here by the option's underlying value (the assessment id itself)
  // rather than its display label, since the label also carries a locale-formatted date.
  await takeCard.locator("select#assessment-picker").selectOption({ value: assessmentId });
  await takeCard.getByRole("button", { name: "Start assessment" }).click();
  await expect(page.getByText("Upload your worked-out solution.")).toBeVisible();

  const fileInput = page.locator('fieldset.question input[type="file"]');
  await expect(fileInput).toHaveCount(1);
  await expect(page.locator("fieldset.question textarea")).toHaveCount(0);

  const tmpFile = path.join(os.tmpdir(), `e2e-file-response-${Date.now()}.txt`);
  fs.writeFileSync(tmpFile, `Playwright E2E upload ${Date.now()}`);
  await fileInput.setInputFiles(tmpFile);
  await page.getByRole("button", { name: "Submit assessment" }).click();
  await expect(page.getByText(/^Submitted\./)).toBeVisible();
  fs.unlinkSync(tmpFile);

  // Trainer side: the grading review pane (RAID.md I-18 sub-item 1's fix) must show a
  // real, clickable file link for this answer -- not empty or raw placeholder text.
  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  await page.goto("/it/trainer/assessments");
  const gradeCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Grade written attempt" }) });
  await gradeCard.getByLabel("Submitted attempt").selectOption({ label: `Arjun Rao · ${title} · submitted` });

  const openFileLink = gradeCard.getByRole("link", { name: "Open submitted file" });
  await expect(openFileLink).toBeVisible();
  await expect(openFileLink).toHaveAttribute("href", /\/local-files\/uploads\/.+/);
});
