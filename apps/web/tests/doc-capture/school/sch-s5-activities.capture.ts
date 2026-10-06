import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S5 (docs/school-crm/documentation-plan.md): DOC-SCH-ACT-001..005, DOC-SCH-SADM-009. Runs after sch-s4.
const ACT = "activities";
const ADM = "admin-schools";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const body = async (page: Page) => (await page.locator("main").first().innerText()).replace(/\s+/g, " ");
// Local (IST) dates for <input type=date|datetime-local>.
const ist = (days: number) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);

async function fresh(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}

async function schedule(p: Page, title: string, when: string, type: string) {
  await p.fill("#activity-title", title);
  await p.fill("#activity-when", when);
  await p.selectOption("#activity-type", { label: type });
  await p.getByRole("button", { name: "Schedule activity" }).click();
}

test("School CRM S5 activities, attendance and feedback", async ({ browser }) => {
  test.setTimeout(600_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));
  const FUTURE = "Docs Career Seminar";
  const PAST = "Docs Parent Orientation";
  const PAST_UNTYPED = "Docs Annual Day Rehearsal";

  // --- ACT-001 schedule (Sunrise, Platinum) ---
  const co = await fresh(browser);
  const p = co.page;
  await signIn(p, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
  await p.goto("/school/coordinator/activities");
  await expect(p.getByRole("heading", { name: "Schedule an activity" })).toBeVisible();
  await p.fill("#activity-title", FUTURE);
  await p.fill("#activity-when", `${ist(7)}T10:00`);
  await p.selectOption("#activity-type", { label: "Career seminar" });
  await shoot(p, ACT, "01-schedule-activity-form.png", { ...opts, center: p.locator("#activity-type") });
  await p.getByRole("button", { name: "Schedule activity" }).click();
  const scheduled = p.getByText(`${FUTURE} scheduled.`);
  await expect(scheduled).toBeVisible();
  await shoot(p, ACT, "02-activity-scheduled.png", { ...opts, center: scheduled });
  await schedule(p, PAST, `${ist(-2)}T10:00`, "Parent orientation");
  await expect(p.getByText(`${PAST} scheduled.`)).toBeVisible();
  await schedule(p, PAST_UNTYPED, `${ist(-3)}T15:00`, "None");
  await expect(p.getByText(`${PAST_UNTYPED} scheduled.`)).toBeVisible();
  // U5: over-long title.
  await schedule(p, "Docs " + "T".repeat(210), `${ist(9)}T10:00`, "None");
  await p.waitForTimeout(2000);
  await say(p, "U5 long title");
  await p.goto("/school/coordinator/activities");
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  console.log(`VERIFY activities list: ${(await body(p)).slice(0, 700)}`);
  await shoot(p, ACT, "03-activities-list.png", opts);

  // --- ACT-002 mark attendance (past orientation) ---
  await p.getByRole("row", { name: new RegExp(PAST) }).getByRole("button", { name: "Mark attendance" }).click();
  const markCard = p.locator(".card, .action-card, section").filter({ has: p.getByRole("heading", { name: "Mark attendance" }) }).last();
  await expect(markCard).toBeVisible();
  const boxes = markCard.getByRole("checkbox");
  console.log(`VERIFY attendance boxes: ${await boxes.count()} checked=${await markCard.locator("input:checked").count()}`);
  await boxes.nth(1).uncheck();
  await boxes.nth(3).uncheck();
  await shoot(p, ACT, "04-mark-attendance.png", { ...opts, element: markCard });
  await markCard.getByRole("button", { name: /Save attendance/ }).click();
  const recorded = p.getByText(/Attendance recorded for \d+ student/);
  await expect(recorded).toBeVisible();
  await say(p, "attendance saved");
  await shoot(p, ACT, "05-attendance-recorded.png", { ...opts, center: recorded });
  // Reopen: does it show the saved marks?
  await p.getByRole("row", { name: new RegExp(PAST) }).getByRole("button", { name: "Mark attendance" }).click();
  console.log(`VERIFY reopened attendance checked=${await markCard.locator("input:checked").count()} of ${await boxes.count()}`);
  await markCard.getByRole("button", { name: "Cancel" }).click();

  // --- ACT-003 give feedback (two tabs to show the duplicate case) ---
  await p.goto("/school/coordinator/feedback?status=awaiting");
  await expect(p.getByRole("heading", { name: "Activity feedback" })).toBeVisible();
  console.log(`VERIFY feedback list: ${(await body(p)).slice(0, 500)}`);
  await shoot(p, ACT, "06-feedback-awaiting.png", opts);
  const second = await co.ctx.newPage();
  await second.goto("/school/coordinator/feedback?status=awaiting");
  await second.getByRole("button", { name: `Give feedback for ${PAST}` }).click().catch(async () => second.getByRole("link", { name: `Give feedback for ${PAST}` }).click());
  await p.getByRole("button", { name: `Give feedback for ${PAST}` }).click().catch(async () => p.getByRole("link", { name: `Give feedback for ${PAST}` }).click());
  const form = p.locator("form").filter({ has: p.getByRole("heading", { name: `Feedback: ${PAST}` }) });
  await expect(form).toBeVisible();
  await form.getByRole("button", { name: "Submit feedback" }).click();
  await p.waitForTimeout(800);
  await say(p, "feedback blank");
  await form.getByLabel("4 – Very good").first().check();
  await form.locator('input[name="satisfaction"][value="5"]').check();
  await form.getByLabel("Trainer / Counsellor (optional)").fill("Docs Trainer Rao");
  await form.getByLabel("Feedback", { exact: true }).fill("Parents asked good questions about university options. Session ran 15 minutes over.");
  await form.getByLabel("Suggestions (optional)").fill("Share the slides with parents afterwards.");
  await shoot(p, ACT, "07-feedback-form.png", { ...opts, element: form });
  await form.getByRole("button", { name: "Submit feedback" }).click();
  const fbSaved = p.getByText(`Feedback saved for ${PAST}.`);
  await expect(fbSaved).toBeVisible();
  await shoot(p, ACT, "08-feedback-saved.png", { ...opts, center: fbSaved });
  // Second tab submits too -> duplicate.
  const form2 = second.locator("form").filter({ has: second.getByRole("heading", { name: `Feedback: ${PAST}` }) });
  await form2.locator('input[name="rating"][value="3"]').check();
  await form2.locator('input[name="satisfaction"][value="3"]').check();
  await form2.getByLabel("Feedback", { exact: true }).fill("Second copy");
  await form2.getByRole("button", { name: "Submit feedback" }).click();
  await second.waitForTimeout(1500);
  await say(second, "feedback duplicate");
  await shoot(second, ACT, "09-feedback-duplicate.png", { ...opts, center: second.getByText(/already been submitted/).first() });
  await second.close();
  await p.goto("/school/coordinator/feedback?status=submitted");
  await p.getByText("View feedback").first().click();
  await shoot(p, ACT, "10-feedback-submitted-view.png", opts);

  // --- Tier denials on scheduling (Bronze / no tier / expired) ---
  const denials: [string, string, string, string][] = [
    [school.schools.bronze.email, "Monthly campus visit", "11-schedule-tier-not-included.png", "bronze"],
    [school.schools.notier.email, "None", "12-schedule-no-tier.png", "notier"],
    ["docs.expired.coordinator@example.test", "Career seminar", "13-schedule-tier-expired.png", "expired"],
  ];
  for (const [email, type, file, label] of denials) {
    const f = await fresh(browser);
    await signIn(f.page, email, "test", /\/school\/coordinator\//);
    await f.page.goto("/school/coordinator/activities");
    await schedule(f.page, `Docs ${label} activity`, `${ist(5)}T11:00`, type);
    await f.page.waitForTimeout(1500);
    await say(f.page, `tier ${label}`);
    await shoot(f.page, ACT, file, { ...opts, center: f.page.locator("#activity-type") });
    await f.ctx.close();
  }
  await co.ctx.close();

  // --- U9 parent notification for the future activity ---
  {
    const f = await fresh(browser);
    await signIn(f.page, "school.parent@edusphere.local", "seed", /\/school\/parent\//);
    await f.page.goto("/school/parent/notifications");
    console.log(`VERIFY U9 parent notification: ${(await body(f.page)).slice(0, 400)}`);
    await f.ctx.close();
  }

  // --- ACT-004 Principal reads feedback ---
  {
    const f = await fresh(browser);
    await signIn(f.page, "school.principal@edusphere.local", "seed", /\/school\/principal\//);
    await f.page.goto("/school/principal/feedback");
    await f.page.getByText("View feedback").first().click();
    console.log(`VERIFY principal feedback: ${(await body(f.page)).slice(0, 500)}`);
    await shoot(f.page, ACT, "14-principal-feedback.png", opts);
    await f.page.selectOption("#feedback-filter", { label: "Awaiting feedback" });
    await f.page.waitForTimeout(1000);
    console.log(`VERIFY principal awaiting: ${(await body(f.page)).slice(0, 300)}`);
    await f.ctx.close();
  }

  // --- SADM-009 Overseas Admin activity feedback ---
  {
    const f = await fresh(browser);
    await signIn(f.page, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
    await f.page.goto("/overseas/admin/activity-feedback");
    await expect(f.page.getByRole("heading", { name: "Activity Feedback", exact: true }).first()).toBeVisible();
    await f.page.waitForTimeout(1000);
    console.log(`VERIFY admin feedback: ${(await body(f.page)).slice(0, 600)}`);
    await shoot(f.page, ADM, "23-activity-feedback-list.png", opts);
    await f.page.fill("#feedback-school-search", "Bronze");
    await f.page.selectOption("#feedback-school", { label: "Docs Bronze School" });
    await f.page.waitForTimeout(1500);
    console.log(`VERIFY admin feedback filtered: ${(await body(f.page)).slice(0, 300)}`);
    await shoot(f.page, ADM, "24-activity-feedback-school-filter.png", opts);
    await f.ctx.close();
  }

  // --- ACT-005 daily attendance (Docs Teacher A) ---
  {
    const f = await fresh(browser);
    const t = f.page;
    await signIn(t, "docs.teacher.a@example.test", "test", /\/school\/teacher\//);
    await t.goto("/school/teacher/attendance");
    await expect(t.getByRole("heading", { name: "Attendance" })).toBeVisible();
    console.log(`VERIFY attendance today: ${(await body(t)).slice(0, 500)}`);
    await shoot(t, ACT, "15-daily-attendance-unmarked.png", opts);
    await t.getByRole("button", { name: "Save attendance" }).click();
    await t.waitForTimeout(800);
    await say(t, "attendance none chosen");
    await t.getByRole("button", { name: "Mark all present" }).click();
    const sets = t.locator("main fieldset");
    await sets.nth(1).getByLabel("Absent").check();
    await sets.nth(2).getByLabel("Late").check();
    await sets.nth(3).getByLabel("Excused").check();
    await shoot(t, ACT, "16-daily-attendance-marked.png", opts);
    // Leave prompt.
    let prompt = "";
    t.once("dialog", async (d) => { prompt = d.message(); await d.dismiss(); });
    await t.fill("#attendance-date", ist(-1));
    await t.getByRole("button", { name: "Show" }).click();
    await t.waitForTimeout(800);
    console.log(`VERIFY leave prompt: "${prompt}"`);
    await t.fill("#attendance-date", ist(0));
    await t.getByRole("button", { name: "Save attendance" }).click();
    const savedMsg = t.getByText(/Attendance saved for \d+ student/);
    await expect(savedMsg).toBeVisible();
    await say(t, "attendance saved");
    await shoot(t, ACT, "17-daily-attendance-saved.png", { ...opts, center: savedMsg });
    // Future date.
    await t.fill("#attendance-date", ist(1));
    await t.waitForTimeout(500);
    console.log(`VERIFY future note: ${(await body(t)).slice(0, 300)}`);
    await shoot(t, ACT, "18-daily-attendance-future-date.png", opts);
    // Past date before the students joined.
    await t.goto(`/school/teacher/attendance?date=${ist(-1)}`);
    console.log(`VERIFY past day: ${(await body(t)).slice(0, 300)}`);
    await shoot(t, ACT, "19-daily-attendance-before-enrolment.png", opts);
    await f.ctx.close();
  }

  school.activities = { future: FUTURE, past: PAST, pastUntyped: PAST_UNTYPED };
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
