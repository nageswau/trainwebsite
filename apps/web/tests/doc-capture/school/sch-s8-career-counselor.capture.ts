import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S8 (docs/school-crm/documentation-plan.md): DOC-SCH-CAR-001..011. Runs after sch-s7.
const CC = "career-counselor";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").first().innerText()).replace(/\s+/g, " ");
const card = (p: Page, heading: string | RegExp) => p.locator(".card, .action-card, section").filter({ has: p.getByRole("heading", { name: heading }) }).last();
const ist = (days: number) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);

async function fresh(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}
async function pick(p: Page, inputId: string, text: string) {
  await p.fill(`#${inputId}`, text);
  await p.getByRole("listbox").getByRole("option", { name: new RegExp(text) }).first().click();
}

test("School CRM S8 career counselor", async ({ browser }) => {
  test.setTimeout(900_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));
  const c = await fresh(browser);
  const p = c.page;
  await signIn(p, "school.careercounselor@edusphere.local", "seed", /\/school\/career-counselor\//);
  console.log(`VERIFY CC dashboard headings: ${JSON.stringify(await p.locator("main h2, main h3").allInnerTexts())}`);
  await shoot(p, CC, "01-dashboard.png", opts);

  // ===== CAR-001 add records =====
  await pick(p, "career-new-student", "Docs Student Ananya");
  await p.selectOption("#career-new-type", { label: "Guidance session" });
  await p.selectOption("#career-new-status", "scheduled");
  await p.fill("#career-new-scheduled", `${ist(3)}T11:00`);
  await p.fill("#career-new-career_interests", "Engineering, Design");
  await p.fill("#career-new-academic_strengths", "Mathematics, Physics");
  await p.selectOption("#career-new-global", { label: "Yes" });
  await shoot(p, CC, "02-add-record-form.png", { ...opts, element: card(p, "Add a record") });
  await p.click("#career-new-save");
  await expect(p.getByText("Record saved.").first()).toBeVisible();
  await shoot(p, CC, "03-record-saved.png", { ...opts, center: p.getByText("Record saved.").first() });

  await pick(p, "career-new-student", "Docs Student Arjun");
  await p.selectOption("#career-new-type", { label: "Counselling note" });
  await p.selectOption("#career-new-status", "completed");
  await p.click("#career-new-save");
  await p.waitForTimeout(800);
  await say(p, "counselling note without notes");
  await p.fill("#career-new-notes", "Discussed stream choice; student prefers PCM with computer science.");
  await p.selectOption("#career-new-parent", { label: "Yes" });
  await p.fill("#career-new-parent-note", "Mother attended.");
  await p.click("#career-new-save");
  await expect(p.getByText("Record saved.").first()).toBeVisible();

  await pick(p, "career-new-student", "Docs Student Arjun");
  await p.selectOption("#career-new-type", { label: "Recommendation" });
  await p.fill("#career-new-notes", "Recommend engineering degrees with a data focus.");
  await p.click("#career-new-save");
  await expect(p.getByText("Record saved.").first()).toBeVisible();
  await p.reload();
  console.log(`VERIFY records: ${(await card(p, "Records").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await shoot(p, CC, "04-records-table.png", { ...opts, element: card(p, "Records") });

  // ===== CAR-002 edit and move status =====
  const ananyaRow = () => card(p, "Records").getByRole("row", { name: /Docs Student Ananya.*Guidance session/ });
  const rid = (await ananyaRow().getByRole("button", { name: /Edit/ }).getAttribute("id"))!.replace("career-edit-", "");
  const f = (page: Page, field: string) => page.locator(`#career-${rid}-${field}`);
  const saveEdit = async (page: Page) => {
    await f(page, "save").click();
    await page.waitForTimeout(1500);
    await say(page, "edit save");
  };
  await ananyaRow().getByRole("button", { name: /Edit/ }).click();
  console.log(`VERIFY status options from Scheduled: ${JSON.stringify(await f(p, "status").locator("option").allInnerTexts())}`);
  await f(p, "status").selectOption("completed");
  await f(p, "notes").fill("Session held. Interested in product design; will try a design workshop.");
  await saveEdit(p);
  await p.reload();
  await expect(ananyaRow()).toContainText("Completed");
  await ananyaRow().getByRole("button", { name: /Edit/ }).click();
  console.log(`VERIFY status options from Completed: ${JSON.stringify(await f(p, "status").locator("option").allInnerTexts())}`);
  await f(p, "status").selectOption("follow_up_required");
  await f(p, "follow").fill(ist(14));
  await shoot(p, CC, "05-edit-record-follow-up.png", { ...opts, element: card(p, /^Edit record for/) });
  await saveEdit(p);
  await p.reload();
  await expect(ananyaRow()).toContainText("Follow-up Required");
  // 409: two tabs edit the same record.
  const other = await c.ctx.newPage();
  await other.goto("/school/career-counselor/dashboard");
  await ananyaRow().getByRole("button", { name: /Edit/ }).click();
  await card(other, "Records").getByRole("row", { name: /Docs Student Ananya.*Guidance session/ }).getByRole("button", { name: /Edit/ }).click();
  console.log(`VERIFY status options from Follow-up: ${JSON.stringify(await f(p, "status").locator("option").allInnerTexts())}`);
  await f(p, "status").selectOption("scheduled");
  await f(p, "scheduled").fill(`${ist(16)}T10:00`);
  await saveEdit(p);
  await f(other, "status").selectOption("completed");
  await f(other, "notes").fill("Follow-up done.");
  await f(other, "save").click();
  await other.waitForTimeout(1500);
  await say(other, "record 409");
  await shoot(other, CC, "06-record-changed-elsewhere.png", { ...opts, center: other.getByRole("button", { name: /Discard my changes and reload/ }) });
  await other.close();

  // ===== CAR-003 career preferences =====
  await p.reload();
  await pick(p, "prefs-student", "Docs Student Ananya");
  await p.waitForTimeout(800);
  await p.fill("#prefs-career_interests", "Product design, Engineering");
  await p.fill("#prefs-preferred_countries", "Germany, Netherlands");
  await p.fill("#prefs-preferred_courses", "Industrial Design");
  await p.selectOption("#prefs-global", { label: "Yes" });
  await card(p, "Career preferences").getByRole("button", { name: "Save preferences" }).click();
  await expect(p.getByText("Career preferences saved.")).toBeVisible();
  await shoot(p, CC, "07-career-preferences-saved.png", { ...opts, element: card(p, "Career preferences") });

  // ===== CAR-004 career goal (360) =====
  const students = await (await p.request.get("/api/v1/school/portfolio-students")).json();
  const ananya = students.find((s: { full_name: string }) => s.full_name === "Docs Student Ananya");
  await p.goto(`/school/career-counselor/students/${ananya.id}/360`);
  await p.click("#career-goal-edit");
  await p.fill("#career-goal-input", "Industrial designer at a product company");
  await shoot(p, CC, "08-career-goal-form.png", opts);
  await p.getByRole("button", { name: "Save" }).first().click();
  await expect(p.getByText("Career goal saved.")).toBeVisible();
  await shoot(p, CC, "09-career-goal-saved.png", opts);
  await p.reload();
  await shoot(p, CC, "09b-career-goal-after-reload.png", opts);

  // ===== CAR-005 skills batches =====
  await p.goto("/school/career-counselor/skills");
  await expect(p.getByRole("heading", { name: "Skills batches", exact: true }).first()).toBeVisible();
  console.log(`VERIFY skills list: ${(await main(p)).slice(0, 500)}`);
  await shoot(p, CC, "10-skills-batches.png", opts);
  await p.selectOption("#skill-batch-module-type", { label: "Soft Skills" });
  await p.fill("#skill-batch-title", "Docs Public Speaking Batch");
  await p.fill("#skill-batch-topic", "Public speaking");
  await p.fill("#skill-batch-trainer-name", "Docs Trainer Mehra");
  await p.fill("#skill-batch-start-date", ist(-7));
  await p.fill("#skill-batch-end-date", ist(-10));
  await p.getByRole("button", { name: "Create batch" }).click();
  await p.waitForTimeout(800);
  await say(p, "batch end before start");
  await p.fill("#skill-batch-end-date", ist(30));
  await shoot(p, CC, "11-create-batch-form.png", { ...opts, element: card(p, "Create a batch") });
  await p.getByRole("button", { name: "Create batch" }).click();
  await p.waitForURL(/\/school\/career-counselor\/skills\/[0-9a-f-]+/);
  const batchUrl = new URL(p.url()).pathname;
  await shoot(p, CC, "12-batch-header.png", opts);

  // ===== CAR-006 edit details =====
  await p.getByRole("button", { name: "Edit details" }).click();
  await p.fill("#skill-edit-trainer", "Docs Trainer Mehra (guest)");
  await p.getByRole("button", { name: "Save details" }).click();
  await expect(p.getByText("Details saved.")).toBeVisible();
  await say(p, "details saved");

  // ===== CAR-007 enrolments =====
  await p.fill("#skill-enrol-filter", "Docs Student");
  const enrolBox = card(p, "Enrol students");
  for (const n of ["Docs Student Ananya", "Docs Student Arjun", "Docs Student Meera", "Docs Student Dev"]) await enrolBox.getByLabel(n).check();
  await shoot(p, CC, "13-enrol-students.png", { ...opts, center: p.locator("#skill-enrol-filter") });
  await enrolBox.getByRole("button", { name: /Enrol 4 student/ }).click();
  await expect(p.getByText("4 students enrolled.")).toBeVisible();
  await p.getByRole("button", { name: "Mark completed Docs Student Ananya" }).click();
  await expect(p.getByText(/Docs Student Ananya: Completed\./)).toBeVisible();
  await p.getByRole("button", { name: "Certify Docs Student Arjun" }).click();
  await shoot(p, CC, "14-certify-confirm.png", { ...opts, center: p.getByRole("button", { name: "Confirm certify Docs Student Arjun" }) });
  await p.getByRole("button", { name: "Confirm certify Docs Student Arjun" }).click();
  await expect(p.getByText(/Docs Student Arjun: Certified\./)).toBeVisible();
  await p.getByRole("button", { name: "Withdraw Docs Student Dev" }).click();
  await expect(p.getByText(/Docs Student Dev: Withdrawn\./)).toBeVisible();
  console.log(`VERIFY enrolments: ${(await card(p, "Students").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await shoot(p, CC, "15-enrolment-statuses.png", { ...opts, element: card(p, "Students") });

  // ===== CAR-008 sessions and attendance =====
  await p.fill("#skill-session-date", ist(-1));
  await p.fill("#skill-session-topic", "Introductions and 2-minute talks");
  await p.getByRole("button", { name: "Add session" }).click();
  await expect(p.getByText(/Session on .* added\./)).toBeVisible();
  const att = card(p, "Sessions and attendance");
  await att.getByRole("button", { name: "Mark all present" }).click();
  const boxes = att.getByRole("checkbox");
  console.log(`VERIFY markable students: ${await boxes.count()}`);
  await boxes.last().uncheck();
  await att.getByRole("button", { name: "Save attendance" }).click();
  await expect(p.getByText(/Attendance saved for/)).toBeVisible();
  await say(p, "batch attendance");
  await shoot(p, CC, "16-session-attendance.png", { ...opts, element: att });

  // ===== CAR-009 assessments and scores =====
  const sc = card(p, "Assessments and scores");
  await p.fill("#skill-assessment-name", "Mid-course presentation");
  await p.fill("#skill-assessment-max", "20");
  await sc.getByRole("button", { name: "Add assessment" }).click();
  await expect(p.getByText("Mid-course presentation added.")).toBeVisible();
  const scoreInputs = sc.locator("input[id^='skill-score-']");
  console.log(`VERIFY score rows: ${await scoreInputs.count()}`);
  await scoreInputs.nth(0).fill("25");
  await sc.getByRole("button", { name: "Save scores" }).click();
  await p.waitForTimeout(800);
  await say(p, "score too high");
  await scoreInputs.nth(0).fill("17");
  if ((await scoreInputs.count()) > 1) await scoreInputs.nth(1).fill("14.5");
  await shoot(p, CC, "17-assessment-scores.png", { ...opts, element: sc });
  await sc.getByRole("button", { name: "Save scores" }).click();
  await expect(p.getByText(/Scores saved for/)).toBeVisible();
  await say(p, "scores saved");

  // ===== CAR-006 close the batch =====
  await p.getByRole("button", { name: "Close batch" }).click();
  await expect(p.getByText("Batch closed.")).toBeVisible();
  console.log(`VERIFY header right after close: ${(await main(p)).slice(0, 260)}`);
  await p.reload();
  console.log(`VERIFY after reload: ${(await main(p)).slice(0, 400)}`);
  await shoot(p, CC, "18-batch-closed.png", opts);
  await p.goto("/school/career-counselor/skills");
  await p.selectOption("#skill-filter-status", { label: "Closed" });
  await p.waitForTimeout(1000);
  console.log(`VERIFY closed filter: ${(await main(p)).slice(0, 300)}`);

  // ===== CAR-010 / 011 funding =====
  await p.goto("/school/career-counselor/funding");
  await expect(p.getByRole("heading", { name: "Funding support", exact: true }).first()).toBeVisible();
  const addCase = async (student: string, type: string, provider: string, amount: string, notes: string) => {
    await pick(p, "funding-new-student", student);
    await p.selectOption("#funding-new-type", { label: type });
    await p.fill("#funding-new-provider", provider);
    await p.fill("#funding-new-amount", amount);
    await p.fill("#funding-new-notes", notes);
  };
  await addCase("Docs Student Ananya", "Scholarship", "DAAD", "€850 per month", "Shortlisted for the design scholarship.");
  await shoot(p, CC, "19-add-funding-case.png", { ...opts, element: card(p, "Add a case") });
  await p.click("#funding-new-save");
  await expect(p.getByText("Case saved.").first()).toBeVisible();
  await addCase("Docs Student Ananya", "Scholarship", "Other", "", "Duplicate");
  await p.click("#funding-new-save");
  await p.waitForTimeout(1000);
  await say(p, "duplicate case");
  await shoot(p, CC, "20-funding-duplicate.png", { ...opts, center: p.getByText(/already has an open/).first() });
  await p.reload();
  await addCase("Docs Student Arjun", "Education loan", "Docs Bank", "₹5,00,000", "Family asked about a loan for engineering abroad.");
  await p.click("#funding-new-save");
  await expect(p.getByText("Case saved.").first()).toBeVisible();
  await p.reload();
  const openCases = card(p, "Open cases");
  await openCases.getByRole("row", { name: /Docs Student Ananya/ }).getByRole("button", { name: /Edit/ }).click();
  const fForm = p.locator("form").filter({ has: p.locator("select[id$='-stage']") }).first();
  console.log(`VERIFY stage options: ${JSON.stringify(await fForm.locator("select[id$='-stage'] option").allInnerTexts())}`);
  await fForm.locator("select[id$='-stage']").selectOption("counselling");
  await shoot(p, CC, "21-update-funding-stage.png", { ...opts, element: card(p, /^Update /) });
  await fForm.getByRole("button", { name: "Save changes" }).click();
  await expect(p.getByText("Case saved.").first()).toBeVisible();
  await p.reload();
  await card(p, "Open cases").getByRole("row", { name: /Docs Student Arjun/ }).getByRole("button", { name: /Edit/ }).click();
  await fForm.locator("select[id$='-stage']").selectOption("closed");
  await fForm.getByRole("button", { name: "Save changes" }).click();
  await p.waitForTimeout(800);
  await say(p, "close without reason");
  await fForm.locator("textarea[id$='-reason'], input[id$='-reason']").first().fill("Family chose to self-fund.");
  await shoot(p, CC, "22-close-funding-case.png", { ...opts, element: card(p, /^Update /) });
  await fForm.getByRole("button", { name: "Save changes" }).click();
  await expect(p.getByText("Case saved.").first()).toBeVisible();
  await p.reload();
  await p.getByText(/Finished cases/).click();
  console.log(`VERIFY funding page: ${(await main(p)).slice(0, 700)}`);
  await shoot(p, CC, "23-funding-open-and-finished.png", opts);
  await c.ctx.close();

  // ===== Empty school portfolio =====
  {
    const f = await fresh(browser);
    await signIn(f.page, "docs.cc.empty@example.test", "test", /\/school\/career-counselor\//);
    console.log(`VERIFY empty CC dashboard: ${(await main(f.page)).slice(0, 400)}`);
    await shoot(f.page, CC, "24-empty-portfolio-dashboard.png", opts);
    await f.page.goto("/school/career-counselor/skills");
    console.log(`VERIFY empty CC skills: ${(await main(f.page)).slice(0, 300)}`);
    await shoot(f.page, CC, "25-empty-portfolio-skills.png", opts);
    await f.ctx.close();
  }

  school.career = { batch: batchUrl, funding: ["Ananya Scholarship (Counselling)", "Arjun Education loan (Closed)"], goal: "Ananya" };
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
