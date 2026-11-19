import { readFileSync } from "node:fs";

import { test, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, mailCount, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S5 (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-LEAD-007..014.
// Runs after itc-s4b. Arjun: follow-ups, calls, meeting, counseling, note. Bhavna: WhatsApp, email. Chirag: returned to the telecaller.
// WhatsApp links are blocked in the browser, so nothing reaches WhatsApp; email goes to the docs stack's Mailpit only.
const root = ITC_ROOT;
const L = "leads";
const A = "docs.itc.a@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const istDate = (days = 0) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const formWith = (p: Page, label: string | RegExp) => p.locator("form", { has: p.getByLabel(label) }).last();

test("IT Counselor CRM S5 lead activity", async ({ browser }) => {
  test.setTimeout(900_000);
  const leads = JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")).leads as Record<string, string>;
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  await ctx.route(/(wa\.me|whatsapp\.com)/, (r) => r.abort());
  const c = await ctx.newPage();
  await signIn(c, A, "test", /\/it\/counselor\/dashboard/, "/it/login");
  const arjun = async () => { await c.goto(`/it/counselor/leads/${leads.arjun}`); await c.waitForTimeout(2000); };

  // --- LEAD-007 follow-ups: one completed now, one left open (overdue in S9) ---
  await arjun();
  for (const [n, when, reason, next] of [[1, `${istDate(1)}T10:00`, "fee_details", "Share the fee plan"], [2, `${istDate(2)}T16:00`, "course_details", "Send the syllabus"]] as const) {
    await sec(c, "Follow-ups").getByRole("button", { name: "Add follow-up" }).click();
    await c.waitForTimeout(800);
    const f = formWith(c, "Due date and time (IST, required)");
    if (n === 1) console.log(`VERIFY LEAD-007 reasons: ${JSON.stringify(await f.getByLabel("Reason (required)").locator("option").allInnerTexts())}`);
    await f.getByLabel("Due date and time (IST, required)").fill(when);
    await f.getByLabel("Reason (required)").selectOption(reason);
    await f.getByLabel("Next action").fill(next);
    await f.getByLabel("Notes").fill("Docs follow-up.");
    if (n === 1) await shoot(c, L, "15-follow-up-form.png", { root, element: f });
    await f.getByRole("button", { name: "Add follow-up" }).click();
    await c.waitForTimeout(1500);
    await say(c, `LEAD-007 added ${n}`);
  }
  const fu = sec(c, "Follow-ups");
  console.log(`VERIFY LEAD-007 list: ${await text(fu)} buttons ${JSON.stringify(await fu.getByRole("button").allInnerTexts())}`);
  await shoot(c, L, "16-follow-ups-list.png", { root, element: fu });
  const done = fu.getByRole("button", { name: /complete|done/i }).first();
  if (await done.count()) {
    await done.click();
    await c.waitForTimeout(1000);
    const df = fu.locator("form").last();
    if (await df.count()) {
      console.log(`VERIFY LEAD-007 complete form: ${await text(df)}`);
      const outcome = df.locator("textarea, input[type=text]").first();
      if (await outcome.count()) await outcome.fill("Shared the fee plan on the call.");
      await shoot(c, L, "17-follow-up-complete-form.png", { root, element: fu });
      await df.getByRole("button").first().click();
      await c.waitForTimeout(1500);
    }
    await say(c, "LEAD-007 completed");
    await shoot(c, L, "18-follow-up-completed.png", { root, element: fu });
  } else console.log("VERIFY LEAD-007 no complete button");

  // --- LEAD-008 calls: log, edit, delete ---
  for (const n of [1, 2]) {
    await sec(c, "Calls").getByRole("button", { name: "Log call" }).click();
    await c.waitForTimeout(800);
    const f = formWith(c, "Outcome (required)");
    if (n === 1) console.log(`VERIFY LEAD-008 outcomes: ${JSON.stringify(await f.getByLabel("Outcome (required)").locator("option").allInnerTexts())} :: ${await text(f)}`);
    await f.getByLabel("Outcome (required)").selectOption(n === 1 ? "interested" : "need_information");
    const nums = f.locator("input[type=number]");
    if (await nums.count()) { await nums.nth(0).fill("6"); if ((await nums.count()) > 1) await nums.nth(1).fill("30"); }
    await f.getByLabel("Remarks").fill(n === 1 ? "Discussed evening batch and fee." : "Asked for the syllabus.");
    if (n === 1) await shoot(c, L, "19-log-call-form.png", { root, element: f });
    await f.getByRole("button", { name: "Save call" }).click();
    await c.waitForTimeout(1500);
    await say(c, `LEAD-008 saved ${n}`);
  }
  const calls = sec(c, "Calls");
  console.log(`VERIFY LEAD-008 list: ${await text(calls)} buttons ${JSON.stringify(await calls.getByRole("button").allInnerTexts())}`);
  await shoot(c, L, "20-calls-list.png", { root, element: calls });
  const edit = calls.getByRole("button", { name: /^Edit/ }).first();
  if (await edit.count()) {
    await edit.click();
    await c.waitForTimeout(800);
    await shoot(c, L, "21-call-edit-form.png", { root, element: calls });
    await calls.getByRole("button", { name: "Cancel" }).first().click();
  }
  const del = calls.getByRole("button", { name: /^Delete/ }).first();
  if (await del.count()) {
    await del.click();
    await c.waitForTimeout(800);
    console.log(`VERIFY LEAD-008 delete confirm: ${await text(calls)}`);
    await shoot(c, L, "22-call-delete-confirm.png", { root, element: calls });
    await calls.getByRole("button", { name: /Yes, delete|Delete call|Confirm/ }).first().click();
    await c.waitForTimeout(1500);
    await say(c, "LEAD-008 deleted");
  }

  // --- LEAD-011 meeting ---
  await sec(c, "Meetings").getByRole("button", { name: "Record meeting" }).click();
  await c.waitForTimeout(800);
  const mf = formWith(c, "Notes (required)");
  await mf.getByLabel("Meeting date and time (IST)").fill(`${istDate(0)}T10:00`);
  await mf.getByLabel("Mode").selectOption("In person");
  await mf.getByLabel("Notes (required)").fill("Met Arjun and his father at the centre; walked through the lab.");
  await shoot(c, L, "23-meeting-form.png", { root, element: mf });
  await mf.getByRole("button", { name: "Save meeting" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-011 saved");
  await shoot(c, L, "24-meeting-saved.png", { root, element: sec(c, "Meetings") });

  // --- LEAD-012 counseling ---
  await sec(c, "Counseling").getByRole("button", { name: "Record counseling" }).click();
  await c.waitForTimeout(1200);
  const cf = formWith(c, "Outcome (required)");
  console.log(`VERIFY LEAD-012 form: ${await text(cf)}`);
  await cf.getByLabel("Outcome (required)").selectOption("interested");
  await cf.getByLabel("Recommended course").selectOption({ label: "Python Full Stack" });
  await cf.getByLabel("Course fee quoted (₹)").fill("45000");
  await cf.getByLabel("Expected joining date").fill(istDate(7));
  await cf.getByLabel("Decision-maker").selectOption("parent");
  await cf.getByLabel("Next follow-up").fill(istDate(2));
  await cf.getByRole("checkbox").first().check();
  await cf.getByLabel("Counselor notes").fill("Keen on the evening batch; father decides on the fee.");
  await shoot(c, L, "25-counseling-form.png", { root, element: cf });
  await cf.getByRole("button", { name: "Save counseling" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-012 saved");
  console.log(`VERIFY LEAD-012 saved: ${await text(sec(c, "Counseling"))}`);
  await shoot(c, L, "26-counseling-saved.png", { root, element: sec(c, "Counseling") });

  // --- LEAD-014 note + activity ---
  await c.getByLabel("Add a note").fill("Father will visit on Saturday to pay the first installment.");
  await c.getByRole("button", { name: "Add note" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-014 note");
  await shoot(c, L, "27-notes.png", { root, element: sec(c, "Notes") });
  console.log(`VERIFY LEAD-014 activity: ${await text(sec(c, "Activity"))}`);
  await shoot(c, L, "28-activity.png", { root, element: sec(c, "Activity") });

  // --- LEAD-009 WhatsApp + LEAD-010 email (Bhavna) ---
  await c.goto(`/it/counselor/leads/${leads.bhavna}`);
  await c.waitForTimeout(2000);
  await c.getByRole("button", { name: "Send WhatsApp" }).click();
  await c.waitForTimeout(1000);
  const wa = c.getByRole("group", { name: "WhatsApp message" });
  console.log(`VERIFY LEAD-009 composer: ${await text(wa)} templates ${JSON.stringify(await wa.getByLabel("Template").locator("option").allInnerTexts())}`);
  const tpl = wa.getByLabel("Template");
  if ((await tpl.locator("option").count()) > 1) await tpl.selectOption({ index: 1 });
  await c.waitForTimeout(500);
  const msg = wa.getByLabel("Message");
  if (!(await msg.inputValue())) await msg.fill("Hi Bhavna, this is Docs IT Counselor A from EduSphere. Shall we talk about the Python Full Stack batch?");
  await shoot(c, L, "29-whatsapp-composer.png", { root, element: wa });
  const popup = c.waitForEvent("popup").catch(() => null);
  await wa.getByRole("link", { name: /Open WhatsApp/ }).click();
  const pop = await popup;
  if (pop) await pop.close();
  await c.waitForTimeout(800);
  await shoot(c, L, "30-whatsapp-confirm.png", { root, element: wa });
  await wa.getByRole("button", { name: "Yes, record as sent" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-009 recorded");

  const before = await mailCount("docs.itlead.bhavna@example.test");
  await c.getByRole("button", { name: "Send email" }).first().click();
  await c.waitForTimeout(1000);
  const ef = formWith(c, "Subject");
  await ef.getByLabel("Template").selectOption({ label: "Course brochure" });
  await c.waitForTimeout(800);
  console.log(`VERIFY LEAD-010 template filled: subject=${await ef.getByLabel("Subject").inputValue()} body=${(await ef.getByLabel("Message").inputValue()).slice(0, 300)}`);
  await shoot(c, L, "31-email-form.png", { root, element: ef });
  await ef.getByRole("button", { name: "Send email" }).click();
  await c.waitForTimeout(2500);
  await say(c, "LEAD-010 sent");
  console.log(`VERIFY LEAD-010 mail arrived: ${(await mailCount("docs.itlead.bhavna@example.test")) > before}`);
  await shoot(c, L, "32-messages-list.png", { root, element: sec(c, "Messages") });

  // --- LEAD-013 return Chirag to the telecaller ---
  await c.goto(`/it/counselor/leads/${leads.chirag}`);
  await c.waitForTimeout(2000);
  await c.getByRole("button", { name: "Return to telecaller" }).click();
  await c.waitForTimeout(800);
  const rf = formWith(c, "Reason for returning");
  await rf.getByLabel("Reason for returning").fill("Wants a weekend batch next quarter; please re-contact in January.");
  await shoot(c, L, "33-return-form.png", { root, center: rf });
  await rf.getByRole("button", { name: "Return lead" }).click();
  await c.waitForTimeout(2000);
  await say(c, "LEAD-013 returned");
  console.log(`VERIFY LEAD-013 after: ${c.url()} :: ${await text(c.locator("main"))}`);
  await shoot(c, L, "34-returned.png", { root });
  await c.goto("/it/counselor/leads");
  await c.waitForTimeout(1500);
  console.log(`VERIFY LEAD-013 list: ${await text(c.locator("main"))}`);
});
