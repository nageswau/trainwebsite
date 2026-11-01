import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S7 (docs/counselor-crm/documentation-plan.md): DOC-CNS-APP-001..010, OFR-001..003, DOC-001..004.
// Runs after cns-s7a (Docs University + courses). Offer on A1 expires TOMORROW and the English test request is due TOMORROW,
// so both are overdue/expired in S9 (owner D3).
const root = COUNSELOR_ROOT;
const FILES = process.env.DOCS_FILES_DIR!;
const file = (n: string) => path.join(FILES, n);
const IST = 5.5 * 3600_000;
const istDate = (days = 0) => new Date(Date.now() + IST + days * 86_400_000).toISOString().slice(0, 10);
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2000);
async function page(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
async function open360(c: Page, search: string) {
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const my = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  await c.fill("#my-students-q", search);
  await my.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await my.getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/students\/[^/?]+/);
  return c.url().split("?")[0];
}
// The application's block in the Evaluate Applications card.
async function evalCard(c: Page, student: string) {
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const ev = c.locator(".action-card").filter({ hasText: "Evaluate Applications" }).first();
  return ev.locator(`xpath=.//h4[normalize-space()='${student}']/ancestor::div[contains(concat(' ',@class,' '),' card ')][1]`).first();
}
async function addApplication(c: Page, base: string, course: RegExp, shotPrefix?: string) {
  await c.goto(`${base}?tab=applications`);
  await c.waitForTimeout(2000);
  await c.locator("summary", { hasText: "Add application" }).click();
  await c.selectOption("#apply-country", { label: "United Kingdom" });
  await c.waitForTimeout(800);
  await c.selectOption("#apply-university", { label: "Docs University -- Docs City" });
  await c.waitForTimeout(1500);
  const courseSel = c.locator("#apply-course");
  const opts = await courseSel.locator("option").allInnerTexts().catch(() => []);
  console.log(`VERIFY APP-001 courses ${JSON.stringify(opts)}`);
  const pick = opts.find((o) => course.test(o));
  if (pick) await courseSel.selectOption({ label: pick });
  await c.selectOption("#apply-intake", { label: "September" });
  await c.selectOption("#apply-intake-year", { label: "2027" });
  const form = c.locator("form").filter({ has: c.locator("#apply-university") });
  if (shotPrefix) await shoot(c, "applications", `${shotPrefix}-add-application-form.png`, { root, element: form });
  await form.getByRole("button", { name: "Create application" }).click();
  await c.waitForTimeout(2000);
  await say(c, "APP-001 create");
  return form;
}

test("Counselor CRM S7 applications, offers, documents", async ({ browser }) => {
  test.setTimeout(1_200_000);
  const c = await page(browser);
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);

  // ===== APP-001/002/003: applications for Asha (A1) and the walk-in student (A2) =====
  const asha = await open360(c, "Asha");
  const f1 = await addApplication(c, asha, /MSc Data Science/, "01");
  await shoot(c, "applications", "02-application-created.png", { root, element: f1 });
  await addApplication(c, asha, /MSc Data Science/);
  await shoot(c, "applications", "03-application-duplicate.png", { root, element: c.locator("form").filter({ has: c.locator("#apply-university") }) });
  await c.goto(`${asha}?tab=applications`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY APP-003 list: ${await text(c.locator("main"))}`);
  await shoot(c, "applications", "04-applications-tab.png", { root });
  const walkin = await open360(c, "Docs Walk-in Student");
  await addApplication(c, walkin, /MBA/);

  // ===== DOC-004 uploads and DOC-003 requests on Asha =====
  await c.goto(`${asha}?tab=documents`);
  await c.waitForTimeout(2500);
  console.log(`VERIFY DOC documents tab: ${await text(c.locator("main"))}`);
  const up = c.locator("form").filter({ has: c.locator("input[type=file]") }).first();
  for (const [type, f] of [["Passport", "docs-passport.pdf"], ["Transcripts", "docs-transcripts.pdf"]] as const) {
    await up.getByLabel("Document type").selectOption({ label: type });
    const uapp = await c.locator("#upload-application option").allInnerTexts();
    const ua = uapp.find((o) => /Docs University/.test(o));
    if (ua) await c.selectOption("#upload-application", { label: ua });
    else console.log(`VERIFY DOC-004 application options ${JSON.stringify(uapp)}`);
    await up.locator("input[type=file]").setInputFiles(file(f));
    if (type === "Passport") await shoot(c, "documents", "07-upload-document-form.png", { root, element: up });
    await up.getByRole("button", { name: "Upload document" }).click();
    await c.waitForTimeout(2500);
    await say(c, `DOC-004 upload ${type}`);
  }
  await shoot(c, "documents", "08-uploaded.png", { root, element: up });
  const req = c.locator("form").filter({ has: c.getByRole("button", { name: "Send request" }) }).first();
  console.log(`VERIFY DOC-003 request form: ${await text(req)}`);
  for (const [type, days] of [["English test", 1], ["SOP", 7]] as const) {
    await req.getByLabel("Document type").selectOption({ label: type });
    await req.getByLabel(/Due date/).fill(istDate(days));
    const appSel = req.getByLabel(/Application/);
    const aopts = await appSel.locator("option").allInnerTexts().catch(() => []);
    const ao = aopts.find((o) => /Docs University/.test(o));
    if (ao) await appSel.selectOption({ label: ao });
    await req.getByLabel(/Note to the student/).fill(type === "English test" ? "Please upload your IELTS result (overall 7.0 or above)." : "Please upload your statement of purpose for MSc Data Science.");
    if (type === "English test") await shoot(c, "documents", "05-request-document-form.png", { root, element: req });
    await req.getByRole("button", { name: "Send request" }).click();
    await c.waitForTimeout(2000);
    await say(c, `DOC-003 request ${type}`);
  }
  const reqCard = c.locator("section, .card, .action-card").filter({ has: c.getByRole("heading", { name: "Document requests" }) }).last();
  await c.getByRole("button", { name: "Cancel request for SOP", exact: true }).click();
  await c.waitForTimeout(1500);
  await say(c, "DOC-003 cancelled SOP");
  await c.reload();
  await c.waitForTimeout(2500);
  await shoot(c, "documents", "06-document-requests.png", { root, element: c.locator("main") });

  // ===== DOC-002 review on the Documents page (Document Verification) =====
  await c.goto("/overseas/counselor/documents");
  await c.waitForTimeout(2500);
  console.log(`VERIFY DOC-002 documents page: ${await text(c.locator("main"))}`);
  await shoot(c, "documents", "03-document-verification.png", { root });
  const review = c.locator(".action-card").filter({ hasText: "Document Verification" }).last();
  for (const [doc, expiry] of [["Passport", "2032-05-31"], ["Transcripts", ""]] as const) {
    const row = review.locator(".card").filter({ hasText: "Docs Lead Asha" }).filter({ hasText: doc }).last();
    await row.getByRole("button", { name: "Review" }).click();
    await c.waitForTimeout(800);
    await row.locator("select[id^='decision-']").selectOption({ label: "Verified" });
    if (expiry) await row.locator("input[id^='expiry-']").fill(expiry);
    await row.locator("textarea[id^='notes-']").fill("Checked against the original at the office.").catch(() => {});
    if (doc === "Passport") { console.log(`VERIFY DOC-002 review form: ${await text(row)}`); await shoot(c, "documents", "04-review-document.png", { root, element: row }); }
    await row.locator("form").getByRole("button").filter({ hasNotText: /Cancel/ }).first().click();
    await c.waitForTimeout(2000);
    await say(c, `DOC-002 reviewed ${doc}`);
  }
  await c.reload();
  await c.waitForTimeout(2000);
  await shoot(c, "documents", "03b-document-verification-after.png", { root });

  // ===== DOC-001 checklist + APP-005 gate on A1 =====
  let a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Document checklist" }).click();
  await c.waitForTimeout(1500);
  console.log(`VERIFY DOC-001 before: ${await text(a1)}`);
  await shoot(c, "documents", "01-checklist-template-match.png", { root, element: a1 });
  await a1.getByRole("button", { name: /Create checklist/ }).first().click();
  await c.waitForTimeout(2000);
  await say(c, "DOC-001 created");
  console.log(`VERIFY DOC-001 after: ${await text(a1)}`);
  await shoot(c, "documents", "02-checklist.png", { root, element: a1 });
  // Gate: Ready for submission while documents are not complete (block mode).
  await a1.getByRole("button", { name: "Update sub-status" }).click();
  await c.waitForTimeout(800);
  const sub = a1.locator("form").filter({ hasText: "Sub-status" }).first();
  console.log(`VERIFY APP-005 options: ${JSON.stringify(await sub.locator("select").first().locator("option").allInnerTexts())}`);
  await sub.locator("select").first().selectOption({ label: "Ready for submission" });
  await sub.getByRole("button", { name: "Update sub-status" }).click();
  await c.waitForTimeout(1800);
  await say(c, "APP-005 gate");
  console.log(`VERIFY APP-005 gate: ${await text(a1)}`);
  await shoot(c, "applications", "09-ready-for-submission-blocked.png", { root, element: a1 });
  await sub.getByRole("button", { name: /Cancel/ }).click().catch(() => {});
  // Mark the two missing documents Not required (English test stays requested from the student).
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Document checklist" }).click();
  await c.waitForTimeout(1500);
  for (const item of ["English test", "SOP"]) {
    const li = a1.locator("li").filter({ hasText: item }).filter({ hasNotText: "Passport Required" }).last();
    await li.getByRole("button", { name: "Mark not required" }).click();
    await c.waitForTimeout(1500);
    await say(c, `DOC-001 ${item} not required`);
  }
  console.log(`VERIFY DOC-001 complete: ${await text(a1)}`);
  await shoot(c, "documents", "02b-checklist-complete.png", { root, element: a1 });

  // APP-004 advance A1 to University Selection.
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Advance stage" }).click();
  const adv = a1.locator("form").filter({ hasText: "Advance to" });
  console.log(`VERIFY APP-004 options: ${JSON.stringify(await adv.locator("select").locator("option").allInnerTexts())}`);
  await adv.locator("select").selectOption({ label: "University Selection" });
  await adv.locator("textarea").fill("Upload your English test result and SOP so we can submit your application.");
  await shoot(c, "applications", "07-advance-stage.png", { root, element: a1 });
  await adv.getByRole("button", { name: "Advance" }).click();
  await c.waitForTimeout(2000);
  await say(c, "APP-004 advanced");
  await shoot(c, "applications", "08-advanced.png", { root, element: (await evalCard(c, "Docs Lead Asha")) });
  for (const label of ["Ready for submission", "Submitted"]) {
    a1 = await evalCard(c, "Docs Lead Asha");
    await a1.getByRole("button", { name: "Update sub-status" }).click();
    const sf = a1.locator("form").filter({ hasText: "Sub-status" }).first();
    await sf.locator("select").first().selectOption({ label });
    await sf.getByRole("button", { name: "Update sub-status" }).click();
    await c.waitForTimeout(2000);
    await say(c, `APP-005 ${label}`);
    if (label === "Ready for submission") await shoot(c, "applications", "09b-ready-for-submission.png", { root, element: await evalCard(c, "Docs Lead Asha") });
  }

  // ===== OFR-001..003 on A1: offer (expires tomorrow), condition, interview =====
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Advance stage" }).click();
  await a1.locator("form").filter({ hasText: "Advance to" }).locator("select").selectOption({ label: "Offer" });
  await a1.locator("form").filter({ hasText: "Advance to" }).getByRole("button", { name: "Advance" }).click();
  await c.waitForTimeout(2000);
  await say(c, "APP-004 advanced to Offer");
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Offers" }).click();
  await c.waitForTimeout(1200);
  await a1.getByRole("button", { name: /Record offer/ }).first().click();
  await c.waitForTimeout(800);
  const of = a1.locator("form").filter({ hasText: "Offer type" }).first();
  console.log(`VERIFY OFR-001 form: ${await text(of)}`);
  await of.getByRole("radio", { name: "Conditional", exact: true }).check();
  await of.getByLabel("Issue date").fill(istDate(0)).catch(() => {});
  await of.getByLabel(/Offer deadline/).fill(istDate(1)).catch(() => {});
  await of.getByLabel(/Conditions/).fill("Final transcript showing 75% or above; IELTS 7.0 overall.").catch(() => {});
  await of.getByLabel("Currency").fill("GBP");
  await of.getByLabel("Tuition fee").fill("26000").catch(() => {});
  await of.getByLabel(/Deposit amount/).fill("5000").catch(() => {});
  await of.getByLabel(/Deposit deadline/).fill(istDate(20)).catch(() => {});
  await of.locator("input[type=file]").setInputFiles(file("docs-offer-letter.pdf"));
  await shoot(c, "offers", "01-record-offer-form.png", { root, element: of });
  await of.getByRole("button", { name: "Save offer" }).click();
  await c.waitForTimeout(2500);
  await say(c, "OFR-001 offer recorded");
  console.log(`VERIFY OFR-001 after: ${await text(a1)}`);
  await shoot(c, "offers", "02-offer-recorded.png", { root, element: a1 });
  // OFR-002 condition.
  const addCond = a1.getByRole("button", { name: /Add condition/ }).first();
  await addCond.click().catch(() => console.log("VERIFY OFR-002 no Add condition button"));
  await c.waitForTimeout(800);
  const cf = a1.locator("form").filter({ hasText: "Owner" }).first();
  console.log(`VERIFY OFR-002 form: ${await text(cf).catch(() => "none")}`);
  await cf.getByLabel("Condition").fill("Submit final semester transcript (75% or above)").catch(() => {});
  await cf.getByLabel("Owner").selectOption({ label: "Student" }).catch(() => {});
  await cf.getByLabel(/Due date/).fill(istDate(14)).catch(() => {});
  await shoot(c, "offers", "03-offer-condition-form.png", { root, element: cf }).catch(() => {});
  await cf.getByRole("button", { name: "Save condition" }).click().catch(() => {});
  await c.waitForTimeout(2000);
  await say(c, "OFR-002 condition");
  await cf.getByLabel("Status").selectOption({ label: "Met" }).catch(() => {});
  await shoot(c, "offers", "04-offer-conditions.png", { root, element: a1 });
  // OFR-003 interview.
  await a1.getByRole("button", { name: "Interviews" }).click();
  await c.waitForTimeout(1000);
  await a1.getByRole("button", { name: "Add interview" }).click().catch(() => {});
  const iv = a1.locator("form").filter({ hasText: "Mode" }).last();
  console.log(`VERIFY OFR-003 form: ${await text(iv).catch(() => "none")}`);
  await iv.locator("input[type=datetime-local]").fill(`${istDate(1)}T15:00`).catch(() => {});
  await iv.getByLabel("Mode").selectOption({ label: "Online" }).catch(() => {});
  await iv.getByLabel(/Link or place/).fill("https://meet.example.test/docs-university-interview").catch(() => {});
  await iv.getByLabel("Result").selectOption({ label: "Passed" }).catch(() => {});
  await iv.getByRole("button", { name: "Save interview" }).click().catch(() => {});
  await c.waitForTimeout(1500);
  await say(c, "OFR-003 result too early");
  await shoot(c, "offers", "06-interview-result-too-early.png", { root, element: iv }).catch(() => {});
  await iv.getByLabel("Result").selectOption({ label: "Awaiting result" }).catch(() => {});
  await iv.getByLabel(/Note for the student/).fill("Online interview with the admissions tutor. Please join 10 minutes early.").catch(() => {});
  await iv.getByRole("button", { name: "Save interview" }).click().catch(() => {});
  await c.waitForTimeout(1500);
  await say(c, "OFR-003 saved");
  await shoot(c, "offers", "05-interviews.png", { root, element: a1 });

  // APP-008 details, APP-009 history.
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Application details" }).click();
  await c.waitForTimeout(1000);
  await a1.getByRole("button", { name: "Edit details" }).click().catch(() => {});
  const df = a1.locator("form").filter({ hasText: "Faculty" }).first();
  console.log(`VERIFY APP-008 form: ${await text(df).catch(() => "none")}`);
  await df.getByLabel("Faculty").fill("Faculty of Science").catch(() => {});
  await df.getByLabel("Campus").fill("Docs City Campus").catch(() => {});
  await df.getByLabel(/Course start date/).fill("2027-09-20").catch(() => {});
  await df.getByLabel(/Application deadline/).fill(istDate(30)).catch(() => {});
  await shoot(c, "applications", "13-application-details-form.png", { root, element: df }).catch(() => {});
  await df.getByRole("button", { name: "Save details" }).click().catch(() => {});
  await c.waitForTimeout(1500);
  await say(c, "APP-008 saved");
  await shoot(c, "applications", "14-application-details.png", { root, element: a1 });
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Status history" }).click();
  await c.waitForTimeout(1500);
  console.log(`VERIFY APP-009 history: ${await text(a1)}`);
  await shoot(c, "applications", "15-status-history.png", { root, element: a1 });

  // ===== A2 (walk-in): APP-007 outcome On hold + Resume, then an accepted offer for S8 =====
  let a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Record outcome" }).click();
  await c.waitForTimeout(800);
  const oc = a2.locator("form").filter({ hasText: "Outcome" }).first();
  console.log(`VERIFY APP-007 form: ${await text(oc)}`);
  await oc.getByLabel("Outcome").selectOption({ label: "On hold" });
  await c.waitForTimeout(500);
  await oc.getByLabel(/Review date/).fill(istDate(14)).catch(() => {});
  await oc.getByLabel(/Reason/).fill("Student waiting for a bank loan decision.").catch(() => {});
  await shoot(c, "applications", "10-record-outcome-on-hold.png", { root, element: a2 });
  await oc.getByRole("button", { name: "Record outcome" }).click();
  await c.waitForTimeout(2000);
  await say(c, "APP-007 on hold");
  a2 = await evalCard(c, "Docs Walk-in Student");
  await shoot(c, "applications", "11-on-hold.png", { root, element: a2 });
  await a2.getByRole("button", { name: "Resume" }).click();
  await c.waitForTimeout(600);
  const rf = a2.locator("form[aria-label='Resume application']");
  await rf.locator("textarea").fill("Bank loan approved; continuing the application.");
  await shoot(c, "applications", "11b-resume-reason.png", { root, element: a2 });
  await rf.getByRole("button", { name: "Resume" }).click();
  await c.waitForTimeout(2000);
  await say(c, "APP-007 resumed");
  await shoot(c, "applications", "12-resumed.png", { root, element: await evalCard(c, "Docs Walk-in Student") });
  a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Advance stage" }).click();
  await a2.locator("form").filter({ hasText: "Advance to" }).locator("select").selectOption({ label: "Offer" });
  await a2.locator("form").filter({ hasText: "Advance to" }).getByRole("button", { name: "Advance" }).click();
  await c.waitForTimeout(2000);
  a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Offers" }).click();
  await c.waitForTimeout(1200);
  await a2.getByRole("button", { name: /Record offer/ }).first().click();
  const of2 = a2.locator("form").filter({ hasText: "Offer type" }).first();
  await of2.getByRole("radio", { name: "Unconditional", exact: true }).check();
  await of2.getByLabel("Issue date").fill(istDate(0)).catch(() => {});
  await of2.getByLabel(/Offer deadline/).fill(istDate(30)).catch(() => {});
  await of2.getByLabel("Currency").fill("GBP");
  await of2.getByLabel("Tuition fee").fill("30000").catch(() => {});
  await of2.getByLabel(/Deposit amount/).fill("3000").catch(() => {});
  await of2.getByLabel(/Deposit deadline/).fill(istDate(20)).catch(() => {});
  await of2.locator("input[type=file]").setInputFiles(file("docs-offer-letter.pdf"));
  await of2.getByRole("button", { name: "Save offer" }).click();
  await c.waitForTimeout(2500);
  await say(c, "OFR-001 A2 offer");
  await a2.getByRole("button", { name: "Record acceptance" }).click();
  await c.waitForTimeout(800);
  await a2.getByRole("button", { name: "Save acceptance" }).click();
  await c.waitForTimeout(2000);
  await say(c, "OFR-001 A2 accepted");
  await shoot(c, "offers", "07-offer-accepted.png", { root, element: a2 });

  // ===== APP-010 agency application (Ananya) and APP-006 journey =====
  const an = await evalCard(c, "Ananya Sharma");
  await an.getByRole("button", { name: "Advance stage" }).click();
  console.log(`VERIFY APP-010 agency advance options: ${JSON.stringify(await an.locator("form").filter({ hasText: "Advance to" }).locator("select").locator("option").allInnerTexts())}`);
  await shoot(c, "applications", "16-agency-application-card.png", { root, element: an });
  const ananya = await open360(c, "Ananya");
  await c.goto(`${ananya}?tab=applications`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY APP-010 ananya apps: ${await text(c.locator("main"))}`);
  await shoot(c, "applications", "17-agency-application-360.png", { root });
  await c.goto(asha);
  await c.waitForTimeout(2500);
  const journey = c.locator("section, .card").filter({ hasText: "Journey stage" }).first();
  console.log(`VERIFY APP-006 journey: ${await text(journey)}`);
  await shoot(c, "applications", "05-journey-stage.png", { root, element: journey });
  await c.goto(`${asha}?tab=applications`);
  await c.waitForTimeout(2000);
  await shoot(c, "applications", "06-applications-tab-after.png", { root });
});
