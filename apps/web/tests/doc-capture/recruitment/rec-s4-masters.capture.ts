import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S4 (docs/recruitment-crm/documentation-plan.md): DOC-REC-MST-001..006, ADM-007, ADM-008, CAN-013 (routing rules).
// Runs after rec-s3. Recruiter A adds a shared template, a screening question and a form template; the Team Lead manages skills,
// catalogues, approves the template, switches on collaborators and adds a routing rule; the Super Admin sets match weights.
const root = REC_ROOT;
const M = "masters";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2000);
const card = (p: Page, heading: string | RegExp) =>
  p.getByRole("heading", typeof heading === "string" ? { name: heading, exact: true } : { name: heading }).first()
    .locator("xpath=ancestor::*[self::section or self::form or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const pick = async (p: Page, field: Locator, typed: string, option: RegExp) => {
  await field.fill(typed);
  await settle(p, 1200);
  await p.getByRole("option", { name: option }).first().click();
};
const TEMPLATE = "Docs interview reminder (Python)";
const QUESTION = "Docs: Have you built REST APIs with Python (Django or FastAPI)?";

test("Recruitment CRM S4 masters and templates", async ({ browser }) => {
  test.setTimeout(900_000);
  // ===== Recruiter A =====
  const a = await ctxPage(browser);
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");

  // MST-001 Skills Master (read)
  await a.goto("/recruiter/skills");
  await settle(a);
  await shoot(a, M, "01-skills-recruiter.png", { root });
  await a.getByLabel("Search skills or aliases").fill("J2EE");
  await a.getByRole("button", { name: "Search" }).click();
  await settle(a, 1500);
  console.log(`VERIFY MST-001 alias search: ${await text(a.locator("main"))}`);
  await shoot(a, M, "02-skills-alias-search.png", { root });

  // MST-004 template library: add a shared WhatsApp template (stays Draft)
  await a.goto("/recruiter/templates");
  await settle(a);
  const add = card(a, "Add a template");
  await add.getByLabel("Channel (required)").selectOption({ label: "WhatsApp" });
  await add.getByLabel("Category (required)").selectOption({ label: "Candidate" });
  await settle(a, 500);
  console.log(`VERIFY MST-004 kinds for Candidate: ${(await add.getByLabel("Kind (required)").locator("option").allInnerTexts()).join(" | ")}`);
  await add.getByLabel("Kind (required)").selectOption({ label: "Interview reminders" });
  await add.getByLabel("Template name (required)").fill(TEMPLATE);
  await add.getByLabel("Purpose").fill("Remind a candidate of a Python developer interview");
  await add.getByLabel("Role type").fill("Python developer");
  await add.getByText(/Shared with the team/).click();
  await add.getByLabel("Message (required)").fill("Hi {name}, a reminder of your interview for {requirement} on {date}.");
  await settle(a, 600);
  await say(a, "MST-004 unknown placeholder");
  await shoot(a, M, "03b-template-unknown-placeholder.png", { root, element: add });
  await add.getByLabel("Message (required)").fill("Hi {name}, a reminder of your interview for {job_title} on {interview_date} at {interview_time} ({interview_mode}). Link: {interview_link}. Reply here if you need to reschedule. – {recruiter}, EduSphere");
  console.log(`VERIFY MST-004 form: ${await text(add)}`);
  await shoot(a, M, "03-template-add.png", { root, element: add });
  await add.getByRole("button", { name: "Add template" }).click();
  await settle(a, 2000);
  await say(a, "MST-004 added");
  await a.getByLabel("Search name or purpose").fill("Docs");
  await a.getByRole("button", { name: "Search", exact: true }).click();
  await settle(a, 1500);
  const list = card(a, "Templates");
  console.log(`VERIFY MST-004 list: ${await text(list)}`);
  await shoot(a, M, "04-template-draft.png", { root, element: list });
  await a.getByLabel("Search name or purpose").fill("");
  await a.getByRole("button", { name: "Search", exact: true }).click();
  await settle(a, 1500);
  await a.getByRole("button", { name: "Preview Company introduction" }).click();
  await settle(a, 1000);
  await a.getByRole("button", { name: "Versions of Company introduction" }).click();
  await settle(a, 1000);
  const intro = a.locator("tr, li, article").filter({ hasText: "Company introduction —" }).first().or(a.locator("main").getByText(/Company introduction — /).first().locator("xpath=ancestor::*[self::tr or self::li or self::div][2]"));
  await intro.scrollIntoViewIfNeeded().catch(() => undefined);
  await shoot(a, M, "05-template-preview-versions.png", { root });

  // MST-006 screening question bank (recruiter)
  await a.goto("/recruiter/screening-bank");
  await settle(a);
  await shoot(a, M, "06-screening-bank.png", { root });
  await a.getByRole("button", { name: "Add question" }).click();
  await settle(a, 800);
  const qf = a.locator("form").filter({ has: a.getByRole("button", { name: "Save question" }) }).first();
  await qf.getByLabel("Question text").fill(QUESTION);
  await qf.getByLabel("Category").selectOption({ label: "Technical skills" });
  await qf.getByLabel("Answer format").selectOption({ label: "Yes / No" });
  await settle(a, 500);
  console.log(`VERIFY MST-006 question form: ${await text(qf)}`);
  await qf.getByLabel("What to look for").fill("Yes, with a project they can describe");
  await qf.getByLabel("Expected answer").fill("Yes").catch(async () => qf.getByLabel("Expected answer").selectOption({ label: "Yes" }));
  await shoot(a, M, "07-screening-question-form.png", { root, element: qf });
  await qf.getByRole("button", { name: "Save question" }).click();
  await settle(a, 2000);
  await say(a, "MST-006 question saved");
  await a.getByRole("button", { name: "New template" }).click();
  await settle(a, 800);
  const tf = a.locator("form").filter({ has: a.getByRole("button", { name: "Save template" }) }).first();
  await tf.getByLabel("Template name").fill("Docs Python developer screening");
  await tf.getByLabel("Question 1", { exact: true }).fill("How many years of Python have you used in paid work?");
  await tf.getByLabel(/^Answer format for question 1/).selectOption({ label: "Number" });
  for (const q of [QUESTION, /notice period/]) {
    const sel = tf.getByLabel(/^Add from the bank/);
    const v = await sel.locator("option", { hasText: q }).first().getAttribute("value");
    await sel.selectOption(v!);
    await tf.getByRole("button", { name: "Add from bank" }).click();
    await settle(a, 500);
  }
  console.log(`VERIFY MST-006 template form: ${await text(tf)}`);
  await shoot(a, M, "08-screening-template-form.png", { root, element: tf });
  await tf.getByRole("button", { name: "Save template" }).click();
  await settle(a, 2000);
  await say(a, "MST-006 template saved");
  await shoot(a, M, "09-screening-templates.png", { root, element: card(a, "Form templates") });

  // ===== Team Lead =====
  const l = await ctxPage(browser);
  await signIn(l, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");

  // MST-002 manage skills
  await l.goto("/recruiter/manager/skills");
  await settle(l);
  await shoot(l, M, "10-skills-manager.png", { root });
  const cs = card(l, "Create skill");
  for (const name of ["Docs FastAPI", "Docs Fast-API"]) {
    await cs.getByLabel("Skill name (required)").fill(name);
    await cs.getByLabel("Category (required)").selectOption({ label: "Programming" });
    if (name === "Docs FastAPI") await shoot(l, M, "11-create-skill.png", { root, element: cs });
    await cs.getByRole("button", { name: "Create skill" }).click();
    await settle(l, 1500);
    await say(l, `MST-002 create ${name}`);
  }
  await l.getByLabel("Search skills or aliases").fill("Docs");
  await l.getByRole("button", { name: "Search", exact: true }).click();
  await settle(l, 1500);
  await l.getByRole("button", { name: "Manage Docs FastAPI" }).click();
  await settle(l, 1200);
  await l.getByLabel("New alias").fill("Fast API");
  await l.getByRole("button", { name: "Add alias" }).click();
  await settle(l, 1500);
  await say(l, "MST-002 alias");
  await pick(l, l.getByRole("combobox", { name: "Related skill" }), "Python", /^Python/);
  await l.getByRole("button", { name: "Add related skill" }).click();
  await settle(l, 1500);
  await say(l, "MST-002 related");
  const panel = l.getByRole("button", { name: "Save skill" }).locator("xpath=ancestor::*[self::section or self::dialog or contains(concat(' ',@class,' '),' card ')][1]");
  console.log(`VERIFY MST-002 manage panel: ${await text(panel)}`);
  await shoot(l, M, "12-manage-skill.png", { root, element: panel });
  await l.getByRole("button", { name: "Close" }).click().catch(() => undefined);
  await settle(l, 800);
  await l.getByRole("button", { name: "Manage Docs Fast-API" }).click();
  await settle(l, 1200);
  await pick(l, l.getByRole("combobox", { name: "Merge into" }), "Docs FastAPI", /^Docs FastAPI/);
  await l.getByRole("button", { name: "Merge Docs Fast-API" }).click();
  await settle(l, 1200);
  console.log(`VERIFY MST-002 merge confirm: ${await text(l.locator("main"))}`.slice(0, 600));
  await shoot(l, M, "13-merge-skill-confirm.png", { root, element: panel.or(l.locator("main")).first() });
  await l.getByRole("button", { name: /Confirm merge/ }).click();
  await settle(l, 2000);
  await say(l, "MST-002 merged");
  await l.getByLabel("Search skills or aliases").fill("Docs");
  await l.getByRole("button", { name: "Search", exact: true }).click();
  await settle(l, 1500);
  console.log(`VERIFY MST-002 after merge: ${await text(l.locator("main table").last())}`);
  await shoot(l, M, "14-skills-after-merge.png", { root, element: l.locator("main table").last() });

  // MST-003 catalogues
  await l.goto("/recruiter/manager/catalogue/lead-sources");
  await settle(l);
  await shoot(l, M, "15-catalogue-lead-sources.png", { root });
  await l.getByRole("link", { name: "Candidate tags", exact: true }).click();
  await settle(l);
  console.log(`VERIFY MST-003 tags url ${l.url()}`);
  await l.getByLabel(/candidate tag name \(required\)/i).fill("Docs Immediate joiner");
  await l.getByRole("button", { name: /^Add candidate tag/i }).click();
  await settle(l, 1500);
  await say(l, "MST-003 tag added");
  await shoot(l, M, "16-catalogue-candidate-tags.png", { root });
  await l.getByRole("link", { name: "Campaigns", exact: true }).click();
  await settle(l);
  await l.getByLabel("Campaign name (required)").fill("Docs Q4 IT hiring push");
  await l.getByLabel("Lead source (required)").selectOption({ label: "LinkedIn" });
  await l.getByLabel("Start date (required)").fill(new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10));
  await l.getByRole("button", { name: "Create campaign" }).click();
  await settle(l, 1500);
  await say(l, "MST-003 campaign");
  await shoot(l, M, "17-catalogue-campaigns.png", { root });
  await l.getByRole("link", { name: "Exchange rates", exact: true }).click();
  await settle(l);
  await l.getByLabel("Currency code (required)").fill("USD");
  await l.getByLabel("Rupees for 1 unit (required)").fill("84");
  await l.getByRole("button", { name: "Save rate" }).click();
  await settle(l, 1500);
  await say(l, "MST-003 rate");
  await shoot(l, M, "18-catalogue-exchange-rates.png", { root });

  // MST-005 approve the recruiter's shared template
  await l.goto("/recruiter/manager/templates");
  await settle(l);
  await l.getByLabel("Search name or purpose").fill("Docs");
  await l.getByRole("button", { name: "Search", exact: true }).click();
  await settle(l, 1500);
  const mlist = card(l, "Templates");
  console.log(`VERIFY MST-005 before: ${await text(mlist)}`);
  await shoot(l, M, "19-template-awaiting-approval.png", { root, element: mlist });
  await mlist.getByRole("button", { name: /^Approve/ }).first().click();
  await settle(l, 1500);
  await say(l, "MST-005 approved");
  await shoot(l, M, "20-template-approved.png", { root, element: mlist });

  // ADM-007 candidate settings
  await l.goto("/recruiter/candidates");
  await settle(l);
  const collab = l.getByText("Allow collaborators on candidates").locator("xpath=ancestor::*[self::section or self::form or contains(concat(' ',@class,' '),' card ')][1]");
  const box = l.getByRole("checkbox", { name: /Allow collaborators on candidates/ });
  console.log(`VERIFY ADM-007 collaborators before: ${await box.isChecked()}`);
  if (!(await box.isChecked())) await box.click();
  await settle(l, 1500);
  await say(l, "ADM-007 collaborators");
  await shoot(l, M, "21-candidate-settings.png", { root });

  // CAN-013 routing
  await l.goto("/recruiter/manager/routing");
  await settle(l);
  await shoot(l, M, "22-routing-empty.png", { root });
  await l.getByLabel("Rule type").selectOption({ label: "Candidate source" });
  await l.getByLabel("Candidate source").selectOption({ label: "Website" });
  await pick(l, l.getByRole("combobox", { name: "Recruiter", exact: true }), "Docs Recruiter A", /Docs Recruiter A/);
  await l.getByRole("button", { name: "Add rule" }).click();
  await settle(l, 1500);
  await say(l, "CAN-013 rule");
  await l.getByRole("radio", { name: /Round robin/ }).check();
  await l.getByRole("button", { name: "Save settings" }).click();
  await settle(l, 1500);
  await say(l, "CAN-013 settings");
  console.log(`VERIFY CAN-013 page: ${await text(l.locator("main"))}`);
  await shoot(l, M, "23-routing-rule.png", { root });

  // ===== Super Admin: ADM-008 match weights =====
  const s = await ctxPage(browser);
  await signIn(s, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await s.goto("/recruiter/requirements");
  await settle(s);
  await s.locator("details.action-card summary", { hasText: "Match weights" }).click();
  await settle(s, 600);
  const mw = s.locator("details.action-card", { hasText: "Match weights" }).first();
  await mw.getByLabel("Skills").fill("45");
  await mw.getByLabel("Experience").fill("20");
  await settle(s, 500);
  console.log(`VERIFY ADM-008 total wrong: ${await text(mw)}`);
  await shoot(s, M, "24-match-weights-total.png", { root, element: mw });
  await mw.getByLabel("Experience").fill("15");
  await mw.getByRole("button", { name: "Save weights" }).click();
  await settle(s, 1500);
  await say(s, "ADM-008 saved");
  await shoot(s, M, "25-match-weights-saved.png", { root, element: mw });
  await mw.getByRole("button", { name: "Use the defaults" }).click();
  await settle(s, 800);
  await mw.getByRole("button", { name: "Save weights" }).click();
  await settle(s, 1500);
  await say(s, "ADM-008 defaults");
  console.log(`VERIFY ADM-008 final: ${await text(mw)}`);
});
