import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S5 = Day 1 (docs/counselor-crm/documentation-plan.md): DOC-CNS-ACT-001..006, CHAT-001, FUP-001, TASK-001, CAL-001, CAL-002.
// Follow-ups and tasks due TOMORROW stay open so they are overdue in S9 (owner D3: real days, no back-dating).
const root = COUNSELOR_ROOT;
const A = "docs.counselor.a@example.test";
const TEL = "docs.telecaller@example.test";
const leads = JSON.parse(readFileSync(process.env.DOCS_CNS_FILE!, "utf8")).leads as Record<string, string>;
const IST = 5.5 * 3600_000;
const istDate = (days = 0) => new Date(Date.now() + IST + days * 86_400_000).toISOString().slice(0, 10);
// datetime-local value in IST, `minutes` from now (rounded up to the next minute) or at a fixed time on a day offset.
const istLocalIn = (minutes: number) => new Date(Math.ceil((Date.now() + minutes * 60_000) / 60_000) * 60_000 + IST).toISOString().slice(0, 16);
const istLocalAt = (days: number, hhmm: string) => `${istDate(days)}T${hhmm}`;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const sec = (p: Page, heading: string) => p.getByRole("heading", { name: heading, exact: true }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");

async function page(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}

test("Counselor CRM S5 activity, follow-ups, tasks, calendar", async ({ browser }) => {
  test.setTimeout(1_200_000);

  // ===== Telecaller books counselling appointments with Docs Counselor A on Esha (returned to them in S4) =====
  const t = await page(browser);
  await signIn(t, TEL, "test", /\/telecaller\//);
  const slots = { complete: istLocalIn(7), noshow: istLocalAt(1, "13:00"), confirm: istLocalAt(1, "11:00"), cancel: istLocalAt(1, "16:00") };
  const startsAt = Date.now() + 8 * 60_000; // only the "complete" slot starts today; the no-show is marked in S9
  // One open appointment per lead, so the telecaller adds three more leads of their own (set-up data).
  const target: Record<string, string> = { complete: leads.esha };
  for (const [name, who, phone] of [["noshow", "Docs Lead Farah", "+91 90000 10106"], ["confirm", "Docs Lead Gita", "+91 90000 10107"], ["cancel", "Docs Lead Hari", "+91 90000 10108"]] as const) {
    await t.goto("/telecaller/leads/new");
    await t.waitForTimeout(1500);
    await t.fill("#new-name", who);
    await t.fill("#new-phone", phone);
    await t.fill("#new-email", `${who.toLowerCase().replaceAll(" ", ".")}@example.test`);
    await t.selectOption("#new-product_id", { label: "UK" });
    await t.selectOption("#new-source", "referral");
    await t.getByRole("button", { name: "Create lead" }).click();
    await t.waitForURL(/\/telecaller\/leads\/(?!new)[^/]+$/);
    target[name] = decodeURIComponent(new URL(t.url()).pathname.split("/").pop() ?? "");
  }
  for (const [name, when] of Object.entries(slots)) {
    await t.goto(`/telecaller/leads/${target[name]}`);
    await t.waitForTimeout(1500);
    await t.getByRole("button", { name: "Book counselling" }).click();
    const f = t.locator("form", { has: t.getByRole("heading", { name: "Book counselling" }) });
    await f.getByLabel("Appointment type").selectOption({ index: 1 });
    await f.getByLabel("Counselor").selectOption({ label: "Docs Counselor A" });
    await f.locator("input[type='datetime-local']").fill(when);
    const mode = f.getByLabel("Mode");
    await mode.selectOption({ index: 1 }).catch(() => {});
    for (const [label, value] of [["Meeting link", "https://meet.example.test/docs-counselling"], ["Location", "EduSphere office"], ["Purpose", `Docs ${name} counselling session`]]) {
      await f.getByLabel(label, { exact: false }).first().fill(value).catch(() => {});
    }
    if (name === "complete") console.log(`VERIFY CAL-001 booking form: ${await text(f)}`);
    await f.getByRole("button", { name: "Book appointment" }).click();
    await t.waitForTimeout(1500);
    await say(t, `CAL-001 booked ${name} ${when}`);
  }

  // ===== Counselor A =====
  const c = await page(browser);
  await signIn(c, A, "test", /\/overseas\/counselor\/dashboard/);
  await c.goto(`/overseas/counselor/leads/${leads.divya}`);
  await c.waitForTimeout(2000);

  // ACT-001 calls.
  const calls = sec(c, "Calls");
  await calls.getByRole("button", { name: "Log call" }).click();
  await c.waitForTimeout(500);
  const cf = calls.locator("form").first();
  console.log(`VERIFY ACT-001 form: ${await text(cf)}`);
  await cf.getByLabel(/^Outcome/).selectOption({ label: "Connected – Interested" }).catch(async () => console.log(`VERIFY outcomes ${JSON.stringify(await cf.getByLabel(/^Outcome/).locator("option").allInnerTexts())}`));
  await cf.getByLabel("Minutes").fill("6").catch(() => {});
  await cf.getByLabel("Remarks").fill("Discussed UK universities for MSc Data Science; student wants fee details.");
  await shoot(c, "activity", "01-log-call-form.png", { root, element: cf });
  await cf.getByRole("button", { name: "Save call" }).click();
  await c.waitForTimeout(1500);
  await say(c, "ACT-001 call logged");
  await calls.getByRole("button", { name: "Log call" }).click();
  const cf2 = calls.locator("form").first();
  await cf2.getByLabel(/^Outcome/).selectOption({ label: "Call Back Requested" });
  await c.waitForTimeout(400);
  console.log(`VERIFY ACT-001 callback form: ${await text(cf2)}`);
  await shoot(c, "activity", "02-log-call-follow-up-required.png", { root, element: cf2 });
  await cf2.getByRole("button", { name: "Cancel" }).click();
  await c.waitForTimeout(500);
  await shoot(c, "activity", "03-calls-list.png", { root, element: sec(c, "Calls") });

  // ACT-002 WhatsApp (record a send; the wa.me tab is closed).
  const msgs = sec(c, "Messages");
  await msgs.getByRole("button", { name: "Send WhatsApp" }).click();
  await c.waitForTimeout(800);
  const wf = c.getByRole("group", { name: "WhatsApp message" });
  console.log(`VERIFY ACT-002 composer: ${await text(wf)}`);
  await wf.getByLabel("Message").fill("Hi Divya, as discussed, I'll share the UK university shortlist and fee details by tomorrow. — Docs Counselor A");
  await shoot(c, "activity", "04-whatsapp-composer.png", { root, element: wf });
  const [popup] = await Promise.all([c.waitForEvent("popup", { timeout: 8000 }).catch(() => null), wf.getByRole("link", { name: /Open WhatsApp/ }).click()]);
  if (popup) { console.log(`VERIFY ACT-002 popup host: ${new URL(popup.url()).host}`); await popup.close(); }
  await c.waitForTimeout(600);
  await shoot(c, "activity", "05-whatsapp-did-you-send.png", { root, element: sec(c, "Messages") });
  await c.getByRole("button", { name: "Yes, record as sent" }).click();
  await c.waitForTimeout(1500);
  await say(c, "ACT-002 recorded");

  // ACT-003 email.
  await msgs.getByRole("button", { name: "Send email" }).click();
  await c.waitForTimeout(800);
  const ef = c.getByRole("form", { name: "Email message" });
  await ef.getByLabel("Subject").fill("Your UK university shortlist");
  await ef.getByLabel("Message").fill("Dear Divya,\n\nThank you for visiting us today. I am preparing a shortlist of UK universities for MSc Data Science and will send the fee details tomorrow.\n\nDocs Counselor A");
  await shoot(c, "activity", "06-email-composer.png", { root, element: ef });
  await ef.getByRole("button", { name: "Send email" }).click();
  await c.waitForTimeout(8000);
  await say(c, "ACT-003 queued");
  console.log(`VERIFY ACT-003 list: ${await text(sec(c, "Messages"))}`);
  await shoot(c, "activity", "07-messages-list.png", { root, element: sec(c, "Messages") });

  // ACT-004 meeting (in the past hour).
  const meet = sec(c, "Meetings");
  await meet.getByRole("button", { name: "Record meeting" }).click();
  const mf = meet.locator("form").first();
  await mf.locator("input[type='datetime-local']").fill(istLocalIn(-60));
  await mf.getByLabel("Mode").selectOption({ label: "In person" });
  await mf.getByLabel(/^Notes/).fill("Walk-in counselling at the office with Divya and her father. Agreed on UK, September 2027 intake.");
  await shoot(c, "activity", "08-record-meeting.png", { root, element: mf });
  await mf.getByRole("button", { name: "Save meeting" }).click();
  await c.waitForTimeout(1500);
  await say(c, "ACT-004 recorded");
  await shoot(c, "activity", "09-meetings-list.png", { root, element: sec(c, "Meetings") });

  // ACT-005 note.
  const notes = sec(c, "Notes");
  await notes.getByLabel("Add a note").fill("Father will fund the course; budget around ₹25 lakh. Prefers universities in Manchester or Birmingham.");
  await notes.getByRole("button", { name: "Add note" }).click();
  await c.waitForTimeout(1500);
  await say(c, "ACT-005 note");
  await shoot(c, "activity", "10-notes.png", { root, element: sec(c, "Notes") });

  // FUP-001 follow-ups (two stay open, due tomorrow; one done, one rescheduled, one cancelled).
  const fu = sec(c, "Follow-ups");
  const addFu = async (when: string, reason: string, next: string) => {
    await fu.getByRole("button", { name: "Add follow-up" }).first().click();
    const ff = fu.locator("form").first();
    await ff.locator("input[type='datetime-local']").fill(when);
    await ff.getByLabel(/^Reason/).selectOption({ label: reason });
    await ff.getByLabel("Next action").fill(next);
    return ff;
  };
  const ff = await addFu(istLocalAt(1, "11:00"), "Need fee details", "Call with the fee breakdown");
  await shoot(c, "follow-ups", "01-add-follow-up.png", { root, element: ff });
  await ff.getByRole("button", { name: "Add follow-up" }).click();
  await c.waitForTimeout(1500);
  await say(c, "FUP-001 added");
  for (const [when, reason, next] of [[istLocalIn(90), "Need to discuss with parents", "Check the father's decision"], [istLocalIn(120), "Comparing courses", "Send course comparison"], [istLocalIn(150), "Waiting for documents", "Collect transcripts"]] as const) {
    const f = await addFu(when, reason, next);
    await f.getByRole("button", { name: "Add follow-up" }).click();
    await c.waitForTimeout(1200);
  }
  console.log(`VERIFY FUP-001 list: ${await text(sec(c, "Follow-ups"))}`);
  const item = (reason: string) => sec(c, "Follow-ups").locator("li, article, .card").filter({ hasText: reason }).first();
  await item("Need to discuss with parents").getByRole("button", { name: "Done" }).click();
  await c.waitForTimeout(1200);
  await say(c, "FUP-001 done");
  await item("Comparing courses").getByRole("button", { name: "Reschedule" }).click();
  await c.waitForTimeout(500);
  await item("Comparing courses").locator("input[type='datetime-local']").fill(istLocalAt(1, "15:00"));
  await item("Comparing courses").getByRole("button", { name: /Save/ }).click();
  await c.waitForTimeout(1200);
  await say(c, "FUP-001 rescheduled");
  await item("Waiting for documents").getByRole("button", { name: "Cancel follow-up" }).click();
  await c.waitForTimeout(500);
  await item("Waiting for documents").getByRole("textbox").first().fill("Student will bring documents to the meeting instead.").catch(() => {});
  await item("Waiting for documents").getByRole("button", { name: "Cancel it" }).click();
  await c.waitForTimeout(1200);
  await say(c, "FUP-001 cancelled");
  await shoot(c, "follow-ups", "02-follow-ups-list.png", { root, element: sec(c, "Follow-ups") });

  // ACT-006 timeline.
  await c.reload();
  await c.waitForTimeout(2500);
  console.log(`VERIFY ACT-006 timeline: ${await text(sec(c, "Activity"))}`);
  await shoot(c, "activity", "11-activity-timeline.png", { root, element: sec(c, "Activity") });

  // One follow-up on Chen too (overdue in S9).
  await c.goto(`/overseas/counselor/leads/${leads.chen}`);
  await c.waitForTimeout(1800);
  const chenFu = sec(c, "Follow-ups");
  await chenFu.getByRole("button", { name: "Add follow-up" }).first().click();
  const cff = chenFu.locator("form").first();
  await cff.locator("input[type='datetime-local']").fill(istLocalAt(1, "12:00"));
  await cff.getByLabel(/^Reason/).selectOption({ label: "Requested counselor call" });
  await cff.getByRole("button", { name: "Add follow-up" }).click();
  await c.waitForTimeout(1200);
  await say(c, "FUP-001 Chen added");

  // TASK-001 my tasks.
  await c.goto("/overseas/counselor/tasks");
  await c.waitForTimeout(1800);
  await shoot(c, "tasks", "01-my-tasks-empty.png", { root });
  const tf = c.locator("form", { has: c.getByLabel("Title") }).first();
  const addTask = async (title: string, due: string, priority: string, about?: RegExp) => {
    await tf.getByLabel("Title").fill(title);
    await tf.getByLabel("Due date").fill(due);
    await tf.getByLabel("Priority").selectOption({ label: priority });
    if (about) {
      const opts = await tf.getByLabel(/About/).locator("option").allInnerTexts();
      const pick = opts.find((o) => about.test(o));
      if (pick) await tf.getByLabel(/About/).selectOption({ label: pick });
      else console.log(`VERIFY TASK about options ${JSON.stringify(opts)}`);
    }
  };
  await addTask("Docs Prepare SOP checklist for Divya", istDate(1), "High", /Divya/);
  await shoot(c, "tasks", "02-add-task.png", { root, element: tf });
  await tf.getByRole("button", { name: "Add task" }).click();
  await c.waitForTimeout(1500);
  await say(c, "TASK-001 added");
  for (const [title, due, pr] of [["Docs Call university admissions", istDate(0), "Medium"], ["Docs Weekly pipeline review", istDate(7), "Low"], ["Docs Book IELTS slot", istDate(0), "Low"]] as const) {
    await addTask(title, due, pr);
    await tf.getByRole("button", { name: "Add task" }).click();
    await c.waitForTimeout(1200);
  }
  await tf.getByLabel("Due date").fill(istDate(-1));
  await tf.getByLabel("Title").fill("Docs Past task");
  await tf.getByRole("button", { name: "Add task" }).click();
  await c.waitForTimeout(800);
  await say(c, "TASK-001 past date");
  await shoot(c, "tasks", "03-task-past-date.png", { root, element: tf });
  await tf.getByLabel("Title").fill("");
  const row = (title: string) => c.locator("li, article, tr").filter({ hasText: title }).last();
  await row("Docs Call university admissions").getByRole("button", { name: "Mark done" }).click();
  await c.waitForTimeout(1200);
  await say(c, "TASK-001 done");
  await row("Docs Book IELTS slot").getByRole("button", { name: "Cancel task" }).click();
  await c.waitForTimeout(500);
  await shoot(c, "tasks", "04-cancel-task-confirm.png", { root, center: row("Docs Book IELTS slot") });
  await c.getByRole("button", { name: "Yes, cancel it" }).click();
  await c.waitForTimeout(1200);
  await say(c, "TASK-001 cancelled");
  await c.reload();
  await c.waitForTimeout(1800);
  console.log(`VERIFY TASK-001 page: ${await text(c.locator("main"))}`);
  await shoot(c, "tasks", "05-my-tasks-bands.png", { root, fullPage: true });

  // CHAT-001 counselor chat.
  await c.goto("/overseas/counselor/counselor-chat");
  await c.waitForTimeout(1800);
  await c.locator("#counselor-chat-student").fill("Docs Lead");
  await c.waitForTimeout(1500);
  console.log(`VERIFY CHAT-001 options: ${JSON.stringify(await c.getByRole("option").allInnerTexts())}`);
  await c.getByRole("option", { name: /Docs Lead Asha/ }).first().click();
  await c.waitForTimeout(1500);
  const chat = c.locator("section, .card, .action-card, form").filter({ has: c.locator("#counselor-chat-student") }).last();
  console.log(`VERIFY CHAT-001 panel: ${await text(chat)}`);
  await shoot(c, "chat", "01-chat-no-messages.png", { root, element: chat });
  await chat.getByRole("textbox").last().fill("Hi Asha, welcome to EduSphere! I'm your counselor. Please set your password from the email we sent, then upload your passport.");
  await chat.getByRole("button", { name: "Reply" }).click();
  await c.waitForTimeout(1800);
  await say(c, "CHAT-001 sent");
  await shoot(c, "chat", "02-chat-sent.png", { root, element: chat });
  await c.reload();
  await c.waitForTimeout(1800);
  await shoot(c, "chat", "03-chat-history-table.png", { root });

  // CAL-002 calendar feed (URL masked by shoot()).
  await c.goto("/overseas/counselor/calendar");
  await c.waitForTimeout(1800);
  await shoot(c, "calendar", "05-calendar-feed-off.png", { root });
  await c.getByRole("button", { name: "Create calendar link" }).click();
  await c.waitForTimeout(1500);
  await say(c, "CAL-002 created");
  await shoot(c, "calendar", "06-calendar-feed-link.png", { root });
  c.once("dialog", (d) => { console.log(`VERIFY CAL-002 confirm: ${d.message()}`); d.dismiss(); });
  await c.getByRole("button", { name: "Create a new link" }).click();
  await c.waitForTimeout(800);
  console.log(`VERIFY CAL-002 after new-link click: ${await text(c.locator("main"))}`);
  await shoot(c, "calendar", "07-calendar-new-link-confirm.png", { root });

  // CAL-001 appointments: wait until the first two have started, then act on all four.
  while (Date.now() < startsAt) await c.waitForTimeout(10_000);
  await c.goto("/overseas/counselor/appointments");
  await c.waitForTimeout(2000);
  console.log(`VERIFY CAL-001 list: ${await text(c.locator("main"))}`);
  await shoot(c, "calendar", "01-lead-appointments.png", { root });
  const card = (purpose: string) => c.locator("article, li, .card").filter({ hasText: purpose }).last();
  await card("Docs confirm counselling session").getByRole("button", { name: "Confirm" }).click();
  await c.waitForTimeout(1500);
  await say(c, "CAL-001 confirmed");
  await card("Docs complete counselling session").getByRole("button", { name: "Mark completed" }).click();
  await c.waitForTimeout(800);
  const done = card("Docs complete counselling session");
  console.log(`VERIFY CAL-001 complete form: ${await text(done)}`);
  await done.getByRole("textbox").first().fill("Explained the UK application timeline; she will decide on universities this week.").catch(() => {});
  await done.getByRole("button", { name: /Mark completed|Save|Confirm/ }).last().click().catch(() => {});
  await c.waitForTimeout(1500);
  await say(c, "CAL-001 completed");
  await shoot(c, "calendar", "02-appointment-completed.png", { root, center: card("Docs complete counselling session") });
  console.log(`VERIFY CAL-001 no-show slot (S9): ${await text(card("Docs noshow counselling session"))}`);
  await card("Docs cancel counselling session").getByRole("button", { name: "Cancel appointment" }).click();
  await c.waitForTimeout(600);
  const cc = card("Docs cancel counselling session");
  await cc.getByLabel(/Reason for cancelling/).fill("Student asked to move to an online session next week.");
  await shoot(c, "calendar", "04-cancel-appointment.png", { root, center: cc });
  await cc.getByRole("button", { name: /Cancel appointment|Confirm|Save/ }).last().click();
  await c.waitForTimeout(1500);
  await say(c, "CAL-001 cancelled");
  await c.reload();
  await c.waitForTimeout(2000);
  await toTop(c.locator("main h1, main h2").first());
  await shoot(c, "calendar", "08-lead-appointments-after.png", { root, fullPage: true });
  console.log(`VERIFY Day 1 = ${istDate(0)}`);
});
