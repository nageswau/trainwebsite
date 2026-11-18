import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S5b (docs/recruitment-crm/documentation-plan.md): DOC-REC-CO-003..009 on Docs Acme Technologies. Runs after rec-s5a.
// WhatsApp opens wa.me, which is blocked here: the send is only recorded. Email goes to Mailpit. The contract records terms only (R3).
const root = REC_ROOT;
const C = "companies";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2000);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const istLocal = (days: number, hhmm: string) => {
  const d = new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
  return `${d}T${hhmm}`;
};
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  await ctx.route(/(wa\.me|whatsapp\.com)/, (r) => r.abort());
  return ctx.newPage();
}

test("Recruitment CRM S5b company page", async ({ browser }) => {
  test.setTimeout(900_000);
  const { acme, beta } = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8")).companies;
  const a = await ctxPage(browser);
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  const open = async () => { await a.goto(`/recruiter/companies/${acme}`); await settle(a, 3000); };

  // ===== CO-003 company page, edit =====
  await open();
  await shoot(a, C, "10-company-page.png", { root });
  await shoot(a, C, "11-company-page-full.png", { root, fullPage: true });
  await a.getByRole("button", { name: "Edit", exact: true }).first().click();
  await settle(a, 800);
  await a.getByLabel("Number of employees").fill("350");
  await a.getByLabel("Head office").fill("Hyderabad");
  await a.getByLabel("Branches").fill("Bengaluru\nPune");
  await a.getByRole("button", { name: "Save changes" }).click();
  await settle(a, 2000);
  await say(a, "CO-003 edit");
  await shoot(a, C, "12-company-edited.png", { root, element: sec(a, "Details") });

  // ===== CO-004 contacts =====
  await open();
  await a.getByRole("button", { name: "Add contact" }).click();
  await settle(a, 800);
  const cf = sec(a, "Contacts");
  await cf.getByLabel("Contact name (required)").fill("Docs Rahul Hiring Manager");
  await cf.getByLabel("Designation").fill("Engineering Manager");
  await cf.getByLabel("Department").fill("Engineering");
  await cf.getByLabel("Role", { exact: true }).selectOption({ label: "Hiring Manager" });
  await cf.getByLabel("Mobile").fill("+91 90000 31002");
  await cf.getByLabel("Email").fill("docs.rahul.hm@example.test");
  await cf.getByLabel("Preferred communication").selectOption({ label: "WhatsApp" });
  await cf.getByLabel("Decision-maker").check();
  await cf.getByLabel("Source").selectOption({ label: "LinkedIn" });
  await shoot(a, C, "13-add-contact-form.png", { root, element: cf });
  await cf.getByRole("button", { name: "Save contact" }).click();
  await settle(a, 2000);
  await say(a, "CO-004 contact saved");
  // duplicate mobile warning
  await a.getByRole("button", { name: "Add contact" }).click();
  await settle(a, 800);
  const cf2 = sec(a, "Contacts");
  await cf2.getByLabel("Contact name (required)").fill("Docs Priya Duplicate");
  await cf2.getByLabel("Mobile").fill("+91 90000 31001");
  await cf2.getByRole("button", { name: "Save contact" }).click();
  await settle(a, 2000);
  await say(a, "CO-004 duplicate");
  await shoot(a, C, "14-contact-duplicate-warning.png", { root, element: cf2 });
  await cf2.getByRole("button", { name: "Cancel" }).click();
  await settle(a, 800);
  console.log(`VERIFY CO-004 contacts: ${await text(sec(a, "Contacts"))}`);
  await shoot(a, C, "15-contacts.png", { root, element: sec(a, "Contacts") });

  // ===== CO-005 calls =====
  await a.getByRole("button", { name: "Log call" }).click();
  await settle(a, 800);
  const call = sec(a, "Calls");
  await call.getByLabel("Contact (required)").selectOption({ label: "Docs Priya HR Lead" });
  await call.getByLabel("Outcome (required)").selectOption({ label: "Connected" });
  await call.getByLabel("Minutes").fill("6");
  await call.getByLabel("Seconds").fill("0");
  await call.getByLabel("Notes").fill("Introduced EduSphere. Priya expects two Python developer openings next month.");
  await call.getByLabel("Next action").fill("Send the company introduction email");
  await shoot(a, C, "16-log-call-form.png", { root, element: call });
  await call.getByRole("button", { name: "Save call" }).click();
  await settle(a, 2000);
  await say(a, "CO-005 call");
  await shoot(a, C, "17-calls.png", { root, element: sec(a, "Calls") });

  // ===== CO-006 follow-ups =====
  await open();
  await a.getByRole("button", { name: "Add follow-up" }).click();
  await settle(a, 800);
  const fu = sec(a, "Follow-ups");
  await fu.getByLabel("Due date and time (IST, required)").fill(istLocal(3, "11:00"));
  await fu.getByLabel("Reason (required)").selectOption({ label: "Follow-up for new requirement" });
  await fu.getByLabel("Priority").selectOption({ label: "High" });
  await fu.getByLabel("Contact").selectOption({ label: "Docs Rahul Hiring Manager" });
  await fu.getByLabel("Notes").fill("Ask for the Python developer JD.");
  await shoot(a, C, "18-add-follow-up-form.png", { root, element: fu });
  await fu.getByRole("button", { name: "Add follow-up" }).last().click();
  await settle(a, 2000);
  await say(a, "CO-006 follow-up added");
  const fus = sec(a, "Follow-ups");
  await fus.getByRole("button", { name: "Done" }).first().click();
  await settle(a, 1500);
  console.log(`VERIFY CO-006 after Done: ${await text(fus)}`);
  await say(a, "CO-006 done");
  await shoot(a, C, "19-follow-ups.png", { root, element: sec(a, "Follow-ups") });

  // ===== CO-007 meetings =====
  await a.getByRole("button", { name: "Schedule meeting" }).click();
  await settle(a, 800);
  const mt = sec(a, "Meetings");
  await mt.getByLabel("Meeting type (required)").selectOption({ label: "Requirement discussion" });
  await mt.getByLabel("Date and time (IST, required)").fill(istLocal(2, "15:00"));
  await mt.getByLabel("Mode (required)").selectOption({ label: "Online" });
  await mt.getByLabel("Meeting link").fill("https://meet.example.test/docs-acme");
  await mt.getByLabel("Contact", { exact: true }).selectOption({ label: "Docs Rahul Hiring Manager" });
  await mt.getByLabel("Purpose").fill("Understand the Python developer requirement and the hiring process.");
  await shoot(a, C, "20-schedule-meeting-form.png", { root, element: mt });
  await mt.getByRole("button", { name: "Schedule meeting" }).last().click();
  await settle(a, 2000);
  await say(a, "CO-007 meeting");
  console.log(`VERIFY CO-007 meetings: ${await text(sec(a, "Meetings"))}`);
  await shoot(a, C, "21-meetings.png", { root, element: sec(a, "Meetings") });

  // ===== CO-008 contract / MoU (terms only) =====
  await a.getByRole("button", { name: "Start contract" }).click();
  await settle(a, 800);
  const ct = sec(a, "Contract / MoU");
  await ct.getByLabel("Status").selectOption({ label: "Proposal Sent" });
  await ct.getByLabel("Agreement type").fill("Recruitment services agreement");
  await ct.getByLabel("Fee basis").selectOption({ label: "Percentage of CTC" });
  await ct.getByLabel("Recruitment fee").fill("8.33");
  await ct.getByLabel("Guarantee (days)").fill("90");
  await ct.getByLabel("Payment terms").fill("Invoice on joining; payable within 30 days.");
  await ct.getByLabel("Replacement policy").fill("Free replacement if the candidate leaves within the guarantee period.");
  await shoot(a, C, "22-contract-form.png", { root, element: ct });
  await ct.getByRole("button", { name: "Start contract" }).last().click();
  await settle(a, 2000);
  await say(a, "CO-008 contract");
  console.log(`VERIFY CO-008 contract: ${await text(sec(a, "Contract / MoU"))}`);
  await shoot(a, C, "23-contract.png", { root, element: sec(a, "Contract / MoU") });

  // ===== CO-009 messages =====
  const msgs = () => sec(a, "Messages");
  await msgs().getByRole("button", { name: "Send email" }).click();
  await settle(a, 1000);
  await msgs().getByLabel("To").selectOption({ label: "Docs Priya HR Lead" }).catch(() => undefined);
  await msgs().getByLabel("Template").selectOption({ label: "Company introduction" });
  await settle(a, 1500);
  await shoot(a, C, "24-send-email.png", { root, element: msgs() });
  await msgs().getByRole("button", { name: "Send email" }).last().click();
  await settle(a, 3000);
  await say(a, "CO-009 email");
  await msgs().getByRole("button", { name: "Send WhatsApp" }).click();
  await settle(a, 1000);
  await msgs().getByLabel("To").selectOption({ label: "Docs Rahul Hiring Manager" }).catch(() => undefined);
  await msgs().getByLabel("Template").selectOption({ label: "Follow-up" });
  await settle(a, 1500);
  await shoot(a, C, "25-send-whatsapp.png", { root, element: msgs() });
  const popup = a.waitForEvent("popup").catch(() => null);
  await msgs().getByRole("link", { name: /Open WhatsApp/ }).click();
  const pg = await popup;
  if (pg) await pg.close();
  await settle(a, 1000);
  await shoot(a, C, "26-whatsapp-confirm.png", { root, element: msgs() });
  await msgs().getByRole("button", { name: "Yes, record as sent" }).click();
  await settle(a, 2000);
  await say(a, "CO-009 whatsapp");
  await msgs().getByRole("button", { name: "LinkedIn message" }).click();
  await settle(a, 1000);
  await msgs().getByLabel("What did you send on LinkedIn?").selectOption({ label: "Connection request" });
  await shoot(a, C, "27-linkedin.png", { root, element: msgs() });
  await msgs().getByRole("button", { name: "Log as sent" }).click();
  await settle(a, 2000);
  await say(a, "CO-009 linkedin");
  console.log(`VERIFY CO-009 messages: ${await text(msgs())}`);
  await shoot(a, C, "28-messages.png", { root, element: msgs() });
  const reply = msgs().getByRole("button", { name: /Log reply/ }).first();
  if (await reply.count()) {
    await reply.click();
    await settle(a, 1000);
    console.log(`VERIFY CO-009 log reply form: ${await text(msgs())}`);
    await shoot(a, C, "29-log-reply-form.png", { root, element: msgs() });
  }

  // ===== CO-003 archive (recruiter) and restore (Team Lead) on Docs Beta Systems =====
  await a.goto(`/recruiter/companies/${beta}`);
  await settle(a, 2500);
  await a.getByRole("button", { name: "Archive", exact: true }).click();
  await settle(a, 800);
  await shoot(a, C, "30-archive-confirm.png", { root });
  await a.getByRole("button", { name: "Yes, archive" }).click();
  await settle(a, 2000);
  await say(a, "CO-003 archived");
  console.log(`VERIFY CO-003 archived page: ${(await text(a.locator("main"))).slice(0, 400)}`);
  const l = await ctxPage(browser);
  await signIn(l, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  await l.goto(`/recruiter/companies/${beta}`);
  await settle(l, 2500);
  await shoot(l, C, "31-archived-company-team-lead.png", { root });
  await l.getByRole("button", { name: /Restore/ }).first().click();
  await settle(l, 800);
  const yes = l.getByRole("button", { name: /Yes, restore/ });
  if (await yes.count()) await yes.click();
  await settle(l, 2000);
  await say(l, "CO-003 restored");
});
