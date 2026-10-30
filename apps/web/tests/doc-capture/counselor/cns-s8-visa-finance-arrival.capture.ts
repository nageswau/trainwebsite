import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// Counselor CRM S8 (docs/counselor-crm/documentation-plan.md): DOC-CNS-VISA-001, FIN-001..003, ARR-001, ARR-002, UNI-001, UNI-002,
// plus the P13 agency-enrolment check. Works on A2 (Docs Walk-in Student, Docs MBA, accepted offer) from S7.
const root = COUNSELOR_ROOT;
const file = (n: string) => path.join(process.env.DOCS_FILES_DIR!, n);
const WALKIN_ID = process.env.DOCS_WALKIN_ID!; // users.id of Docs Walk-in Student (looked up by the runner)
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
async function evalCard(c: Page, student: string) {
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const ev = c.locator(".action-card").filter({ hasText: "Evaluate Applications" }).first();
  return ev.locator(`xpath=.//h4[normalize-space()='${student}']/ancestor::div[contains(concat(' ',@class,' '),' card ')][1]`).first();
}
async function visaCard(c: Page, student: string) {
  await c.goto("/overseas/counselor/visa");
  await c.waitForTimeout(2500);
  const vc = c.locator(".action-card").filter({ hasText: "Visa Cases" }).last();
  return vc.locator(".card, li, article").filter({ hasText: student }).last();
}

test("Counselor CRM S8 visa, finance, arrival, universities", async ({ browser }) => {
  test.setTimeout(1_200_000);

  // ===== Set-up: the Overseas Admin records a manual fee for the walk-in student (FIN-002/003) =====
  const a = await page(browser);
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/overseas/admin/payments");
  await a.waitForTimeout(2000);
  await a.fill("[id='Create payment due-user_id']", WALKIN_ID);
  await a.waitForTimeout(800);
  await a.getByRole("option").first().click().catch(() => {});
  await a.fill("[id='Create payment due-reference_type']", "Docs counselling fee");
  await a.fill("[id='Create payment due-amount']", "15000");
  await a.fill("[id='Create payment due-currency']", "INR");
  await a.locator("[id='Create payment due-provider']").selectOption("manual").catch(() => {});
  await a.locator("[id='Create payment due-status']").selectOption("pending").catch(() => {});
  await a.locator("[id='Create payment due-due_date']").fill(istDate(10)).catch(() => {});
  await a.getByRole("button", { name: "Create payment due" }).click();
  await a.waitForTimeout(2000);
  await say(a, "setup payment due");

  const c = await page(browser);
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);

  // ===== FIN-001 deposit on A2 =====
  let a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Offers" }).click();
  await c.waitForTimeout(1500);
  await a2.getByRole("button", { name: /Record deposit/ }).click();
  await c.waitForTimeout(800);
  const dep = a2.locator("form").filter({ hasText: "deposit required" }).first();
  console.log(`VERIFY FIN-001 form: ${await text(dep)}`);
  await dep.getByLabel("Yes").check().catch(() => {});
  await dep.getByLabel("Amount").fill("3000").catch(() => {});
  await dep.getByLabel("Currency").fill("GBP").catch(async () => dep.getByLabel("Currency").selectOption({ label: "GBP" }).catch(() => {}));
  await dep.getByLabel(/Due date/).fill(istDate(20)).catch(() => {});
  await dep.getByLabel("Payment status").selectOption({ label: "Pending" }).catch(() => {});
  await shoot(c, "finance", "01-record-deposit.png", { root, element: dep });
  await dep.getByRole("button", { name: "Save deposit" }).click();
  await c.waitForTimeout(2000);
  await say(c, "FIN-001 saved");
  await shoot(c, "finance", "02-deposit-recorded.png", { root, element: a2 });

  // ===== FIN-002/003 Finance tab =====
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const my = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  await c.fill("#my-students-q", "Docs Walk-in Student");
  await my.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await my.getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/students\/[^/?]+/);
  const walkin = c.url().split("?")[0];
  await c.goto(`${walkin}?tab=finance`);
  await c.waitForTimeout(2500);
  console.log(`VERIFY FIN-002 finance: ${await text(c.locator("main"))}`);
  await shoot(c, "finance", "03-finance-tab.png", { root, element: c.locator("main") });
  const fileInputs = c.locator("main input[type=file]");
  console.log(`VERIFY FIN-003 file inputs: ${await fileInputs.count()}`);
  for (let i = 0; i < (await fileInputs.count()); i++) {
    const inp = fileInputs.nth(i);
    const box = inp.locator("xpath=ancestor::*[self::form or self::div][1]");
    await inp.setInputFiles(file(i === 0 ? "docs-passport.pdf" : "docs-transcripts.pdf").replace("passport", "evidence").replace("transcripts", "evidence"));
    await box.getByRole("button", { name: /Upload receipt|Replace receipt/ }).first().click().catch(async () => c.getByRole("button", { name: /Upload receipt/ }).nth(i).click());
    await c.waitForTimeout(2000);
    await say(c, `FIN-003 upload ${i}`);
  }
  await c.reload();
  await c.waitForTimeout(2500);
  console.log(`VERIFY FIN-003 after: ${await text(c.locator("main"))}`);
  await shoot(c, "finance", "04-receipts-uploaded.png", { root, element: c.locator("main") });

  // ===== VISA-001 prerequisites: passport tied to A2, then passport + offer letter verified =====
  await c.goto(`${walkin}?tab=documents`);
  await c.waitForTimeout(2500);
  const up = c.locator("form").filter({ has: c.locator("#upload-application") }).first();
  await up.getByLabel("Document type").selectOption({ label: "Passport" });
  const uapp = await c.locator("#upload-application option").allInnerTexts();
  await c.selectOption("#upload-application", { label: uapp.find((o) => /Docs University/.test(o))! });
  await up.locator("input[type=file]").setInputFiles(file("docs-passport.pdf"));
  await up.getByRole("button", { name: "Upload document" }).click();
  await c.waitForTimeout(2500);
  await say(c, "VISA-001 passport uploaded");
  await c.goto("/overseas/counselor/documents");
  await c.waitForTimeout(2500);
  const review = c.locator(".action-card").filter({ hasText: "Document Verification" }).last();
  for (const [doc, expiry] of [["Passport", "2033-01-31"], ["Offer letter", ""]] as const) {
    const row = review.locator(".card").filter({ hasText: "Docs Walk-in Student" }).filter({ hasText: doc }).last();
    await row.getByRole("button", { name: "Review" }).click();
    await c.waitForTimeout(800);
    await row.locator("select[id^='decision-']").selectOption({ label: "Verified" });
    if (expiry) await row.locator("input[id^='expiry-']").fill(expiry);
    await row.locator("form").getByRole("button").filter({ hasNotText: /Cancel/ }).first().click();
    await c.waitForTimeout(2000);
    await say(c, `VISA-001 verified ${doc}`);
  }

  // ===== VISA-001 on A2 =====
  let v = await visaCard(c, "Docs Walk-in Student");
  console.log(`VERIFY VISA-001 page: ${await text(c.locator("main"))}`);
  await shoot(c, "visa", "01-visa-page.png", { root });
  await v.getByLabel(/Checklist items/).fill("Passport, Offer letter");
  await shoot(c, "visa", "02-start-visa-case.png", { root, element: v });
  await v.getByRole("button", { name: "Start visa case" }).click();
  await c.waitForTimeout(2000);
  await say(c, "VISA-001 started");
  const steps: [string, Record<string, string>][] = [
    ["Preparing", { "Readiness review date": istDate(2), "Visa category": "Student visa" }],
    ["Appointment booked", { "Appointment date": istDate(-1), "Appointment place": "VFS Global, Docs City" }],
    ["Submitted", { "Submission date": istDate(-1), "Visa application reference": "DOCS-GWF-000123", "Expected decision date": istDate(14) }],
    ["Decision pending", {}],
  ];
  for (const [status, fields] of steps) {
    v = await visaCard(c, "Docs Walk-in Student");
    await v.getByLabel("Next status").selectOption({ label: status });
    for (const [label, value] of Object.entries(fields)) await v.getByLabel(label).fill(value).catch(() => console.log(`VERIFY visa field missing ${label}`));
    if (status === "Submitted") await shoot(c, "visa", "03-visa-case-submitted-form.png", { root, element: v });
    await v.getByRole("button", { name: /Save visa case/ }).click();
    await c.waitForTimeout(2000);
    await say(c, `VISA-001 ${status}`);
  }
  v = await visaCard(c, "Docs Walk-in Student");
  await v.getByLabel("Next status").selectOption({ label: "Approved" });
  await c.waitForTimeout(600);
  await v.getByLabel(/Decision date/).fill(istDate(0)).catch(() => {});
  await v.getByLabel(/Next steps/).fill("Book flights and accommodation; arrive before orientation week.").catch(() => {});
  console.log(`VERIFY VISA-001 decision form: ${await text(v)}`);
  await shoot(c, "visa", "04-record-decision.png", { root, element: v });
  await v.getByRole("button", { name: /Record decision|Save visa case/ }).click();
  await c.waitForTimeout(800);
  await c.getByRole("button", { name: /Yes|Confirm|Record decision/ }).last().click().catch(() => {});
  await c.waitForTimeout(2000);
  await say(c, "VISA-001 approved");
  v = await visaCard(c, "Docs Walk-in Student");
  await shoot(c, "visa", "05-visa-approved.png", { root, element: v });

  // ===== ARR-001 enrolment on A2 =====
  a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Enrolment" }).click();
  await c.waitForTimeout(1000);
  await a2.getByRole("button", { name: /Confirm enrolment/ }).first().click();
  await c.waitForTimeout(800);
  const en = a2.locator("form").filter({ hasText: "Enrolment date" }).first();
  console.log(`VERIFY ARR-001 form: ${await text(en)}`);
  await en.getByLabel("Enrolment date").fill(istDate(0));
  await en.getByLabel("Course start date").fill("2027-09-20").catch(() => {});
  await en.getByLabel(/University student number/).fill("DOCS-2027-0042").catch(() => {});
  await en.locator("input[type=file]").setInputFiles(file("docs-offer-letter.pdf"));
  await en.getByLabel(/pre-enrolment checklist is complete/).check();
  await shoot(c, "arrival", "01-confirm-enrolment-form.png", { root, element: en });
  await en.getByRole("button", { name: "Continue" }).click();
  await c.waitForTimeout(800);
  await shoot(c, "arrival", "02-confirm-enrolment-step.png", { root, element: a2 });
  await a2.getByRole("button", { name: "Yes, confirm enrolment" }).click();
  await c.waitForTimeout(2500);
  await say(c, "ARR-001 confirmed");
  await shoot(c, "arrival", "03-enrolment-confirmed.png", { root, element: await evalCard(c, "Docs Walk-in Student") });

  // ===== ARR-002 arrival and orientation =====
  a2 = await evalCard(c, "Docs Walk-in Student");
  console.log(`VERIFY ARR-002 card: ${await text(a2)}`);
  await a2.getByRole("button", { name: "Arrival and orientation" }).click();
  await c.waitForTimeout(800);
  await a2.getByRole("button", { name: /Record arrival/ }).click();
  const ar = a2.locator("form").filter({ hasText: "Arrival date" }).first();
  await ar.getByLabel("Arrival date").fill(istDate(0));
  await ar.getByLabel("Arrival confirmed").check();
  await ar.getByLabel("Orientation attended").check();
  await ar.getByLabel(/Notes/).fill("Student messaged from the campus accommodation office.");
  await shoot(c, "arrival", "04-record-arrival.png", { root, element: ar });
  await ar.getByRole("button", { name: "Save arrival" }).click();
  await c.waitForTimeout(2000);
  await say(c, "ARR-002 saved");
  await shoot(c, "arrival", "05-arrival-saved.png", { root, element: await evalCard(c, "Docs Walk-in Student") });

  // ===== P13 agency enrolment: advance Ananya to Offer, open the Enrolment form (not confirmed) =====
  let an = await evalCard(c, "Ananya Sharma");
  await an.getByRole("button", { name: "Advance stage" }).click();
  await an.locator("form").filter({ hasText: "Advance to" }).locator("select").selectOption({ label: "Offer" });
  await an.locator("form").filter({ hasText: "Advance to" }).getByRole("button", { name: "Advance" }).click();
  await c.waitForTimeout(2000);
  await say(c, "P13 Ananya advanced to Offer");
  an = await evalCard(c, "Ananya Sharma");
  await an.getByRole("button", { name: "Enrolment" }).click().catch(() => console.log("VERIFY P13 no Enrolment button"));
  await c.waitForTimeout(1000);
  await an.getByRole("button", { name: /Confirm enrolment/ }).first().click().catch(() => console.log("VERIFY P13 no Confirm enrolment"));
  await c.waitForTimeout(800);
  console.log(`VERIFY P13 agency enrolment panel: ${await text(an)}`);
  await shoot(c, "arrival", "06-agency-enrolment-form.png", { root, element: an });

  // ===== UNI-001/002 =====
  await c.goto("/overseas/counselor/universities");
  await c.waitForTimeout(2000);
  await shoot(c, "universities", "01-partner-universities.png", { root });
  await c.getByLabel(/Search by name or city/).fill("Docs");
  await c.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await shoot(c, "universities", "02-search.png", { root });
  await c.getByRole("link", { name: /Docs University/ }).first().click();
  await c.waitForURL(/\/universities\/[^/]+$/);
  await c.waitForTimeout(2500);
  console.log(`VERIFY UNI-002: ${await text(c.locator("main"))}`);
  await shoot(c, "universities", "03-university-360.png", { root });
  await shoot(c, "universities", "04-university-360-full.png", { root, element: c.locator("main") });
});
