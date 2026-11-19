import { readFileSync } from "node:fs";

import { test, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S4b (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-LEAD-001..006, LEAD-015, APPT-001 (counselor side).
// Runs after itc-s4a. Counselor A works Docs IT Lead Arjun (details, next action, Qualified, qualification) and confirms Esha's appointment.
const root = ITC_ROOT;
const L = "leads";
const A = "docs.itc.a@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const istDate = (days = 0) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
// A lead-page section: the nearest section / card around its heading.
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const formWith = (p: Page, label: string | RegExp) => p.locator("form", { has: p.getByLabel(label) }).last();

test("IT Counselor CRM S4b leads", async ({ browser }) => {
  test.setTimeout(900_000);
  const leads = JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")).leads as Record<string, string>;
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const c = await ctx.newPage();
  await signIn(c, A, "test", /\/it\/counselor\/dashboard/, "/it/login");

  // --- LEAD-001 My leads list + filters ---
  await c.goto("/it/counselor/leads");
  await c.waitForTimeout(2000);
  console.log(`VERIFY LEAD-001 list: ${await text(c.locator("main"))}`);
  await shoot(c, L, "01-my-leads.png", { root });
  await c.getByLabel("Priority").selectOption("hot");
  await c.waitForTimeout(1500);
  console.log(`VERIFY LEAD-001 filtered hot: ${await text(c.locator("main"))}`);
  await shoot(c, L, "02-my-leads-filter-hot.png", { root });

  // --- LEAD-002 lead page layout (Arjun) ---
  await c.goto(`/it/counselor/leads/${leads.arjun}`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY LEAD-002 page: ${await text(c.locator("main"))}`);
  await shoot(c, L, "03-lead-page-top.png", { root });
  await shoot(c, L, "04-lead-page-full.png", { root, fullPage: true } as never);

  // --- LEAD-003 edit lead details ---
  await sec(c, "Lead details").getByRole("button", { name: "Edit details" }).click();
  await c.waitForTimeout(800);
  const df = formWith(c, "Preferred contact method");
  await df.getByLabel("Preferred contact method").selectOption("call");
  await df.getByLabel("Marketing consent").selectOption("yes");
  await shoot(c, L, "05-edit-details-form.png", { root, element: df });
  await df.getByRole("button", { name: "Save details" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-003 saved");
  await shoot(c, L, "06-lead-details-saved.png", { root, element: sec(c, "Lead details") });

  // --- LEAD-004 next action ---
  await c.getByRole("button", { name: "Set next action" }).click();
  await c.waitForTimeout(800);
  const nf = formWith(c, "Action");
  await nf.getByLabel("Action").fill("Call Arjun to discuss evening batch timings");
  await nf.getByLabel("Due date").fill(istDate(1));
  await shoot(c, L, "07-next-action-form.png", { root, element: sec(c, "Next action") });
  await nf.getByRole("button", { name: "Save next action" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-004 saved");
  await shoot(c, L, "08-next-action-saved.png", { root, element: sec(c, "Next action") });

  // --- LEAD-005 change stage -> Qualified ---
  await c.getByRole("button", { name: "Change stage" }).click();
  await c.waitForTimeout(800);
  const stage = c.getByLabel("New stage for Docs IT Lead Arjun");
  console.log(`VERIFY LEAD-005 options: ${JSON.stringify(await stage.locator("option").allInnerTexts())}`);
  await stage.selectOption("qualified");
  const sf = c.locator("form", { has: stage });
  await sf.getByLabel("Reason (optional)").fill("Eligible graduate, wants an evening batch.");
  await shoot(c, L, "09-change-stage-form.png", { root, element: sec(c, "Stage") });
  await sf.getByRole("button", { name: "Save" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-005 qualified");
  await shoot(c, L, "10-stage-qualified.png", { root });

  // --- LEAD-006 qualification ---
  await sec(c, "Qualification").getByRole("button", { name: "Edit qualification" }).click();
  await c.waitForTimeout(800);
  const qf = formWith(c, "Current college/company");
  await qf.getByLabel("Current college/company").fill("Docs Engineering College");
  await qf.getByLabel("Passing year").fill("2025");
  await qf.getByLabel("Work experience (years)").fill("0");
  await qf.getByLabel("Current skill level").selectOption("beginner");
  await qf.getByLabel("Career objective").fill("Junior Python developer");
  await qf.getByLabel("Preferred batch").fill("Evening");
  await qf.getByLabel("Budget range").fill("INR 40,000-50,000");
  await qf.getByRole("radio").first().check();
  console.log(`VERIFY LEAD-006 modes: ${await text(qf.locator("fieldset").last()).catch(() => "?")}`);
  await shoot(c, L, "11-qualification-form.png", { root, element: qf });
  await qf.getByRole("button", { name: "Save qualification" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-006 saved");
  await shoot(c, L, "12-qualification-saved.png", { root, element: sec(c, "Qualification") });

  // --- LEAD-015 student and milestones; Student account before/after Qualified ---
  console.log(`VERIFY LEAD-015: ${await text(sec(c, "Student and milestones"))}`);
  await shoot(c, L, "13-student-and-milestones.png", { root, element: sec(c, "Student and milestones") });
  console.log(`VERIFY CONV student account (qualified): ${await text(sec(c, "Student account"))}`);
  await c.goto(`/it/counselor/leads/${leads.bhavna}`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY CONV student account (assigned): ${await text(sec(c, "Student account"))}`);
  await shoot(c, L, "14-student-account-not-qualified.png", { root, element: sec(c, "Student account") });

  // --- APPT-001 counselor side ---
  await c.goto("/it/counselor/appointments");
  await c.waitForTimeout(2000);
  console.log(`VERIFY APPT-001 list: ${await text(c.locator("main"))}`);
  await shoot(c, "appointments", "02-lead-appointments.png", { root });
  const confirm = c.getByRole("button", { name: /^Confirm/ }).first();
  if (await confirm.count()) {
    await confirm.click();
    await c.waitForTimeout(1500);
    await say(c, "APPT-001 confirmed");
    console.log(`VERIFY APPT-001 after confirm: ${await text(c.locator("main"))}`);
    await shoot(c, "appointments", "03-appointment-confirmed.png", { root });
  } else console.log("VERIFY APPT-001 no Confirm button");
  await c.goto(`/it/counselor/leads/${leads.esha}`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY APPT-001 esha lead page: ${await text(c.locator("main"))}`);
});
