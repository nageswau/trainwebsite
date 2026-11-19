import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S11a (docs/recruitment-crm/documentation-plan.md): DOC-REC-HIRE-006/007/009, INT-001 (upcoming), CAND-007 (upcoming).
// Runs after rec-s10a. Recruiter A schedules a Technical Round for Docs Candidate Kiran and an HR Round for Docs Candidate Nisha (after
// confirming her review), both with Docs Interviewer, reschedules Nisha's; the Team Lead saves the interview automation.
const root = REC_ROOT;
const H = "hiring";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, h: string | RegExp) =>
  p.getByRole("heading", { name: h, exact: typeof h === "string" }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const ctrls = async (l: Locator) => JSON.stringify([...new Set((await l.locator("button, a").evaluateAll((els) => els.map((e) => (e.getAttribute("aria-label") || e.textContent || "").trim()))).filter(Boolean))]);
const fields = (l: Locator) => l.evaluate((el) => [...el.querySelectorAll("input, select, textarea")].map((e) => {
  const f = e as HTMLInputElement;
  const lab = (f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.textContent?.trim()) || f.getAttribute("aria-label") || f.closest("label")?.textContent?.trim() || f.name;
  const o = f.tagName === "SELECT" ? " [" + [...(f as unknown as HTMLSelectElement).options].map((x) => x.text).join("|") + "]" : "";
  return `${f.type} "${(lab ?? "").slice(0, 70)}"${o}`;
}));
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}
const plusDays = (n: number) => new Date(Date.now() + 5.5 * 3600_000 + n * 86_400_000).toISOString().slice(0, 10);
async function as(browser: Browser, who: "a" | "lead" | "int") {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  p.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  if (who === "lead") await signIn(p, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  else if (who === "a") await signIn(p, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  else await signIn(p, "docs.rec.interviewer@example.test", "test", /\/it\/interviewer\/dashboard/, "/it/login");
  return p;
}

test("Recruitment CRM S11a schedule interviews", async ({ browser }) => {
  test.setTimeout(1_500_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const a = await as(browser, "a");
  const url = `/recruiter/requirements/${ids.requirements.python}`;
  const open = async () => { await a.goto(url); await settle(a, 3500); };
  const cands = () => sec(a, /^Candidates \(/);

  async function schedule(who: string, round: string, day: string, time: string, shot: string | null, contact: string) {
    await open();
    await cands().getByRole("button", { name: `Interviews of ${who}` }).click();
    await settle(a, 1500);
    await cands().getByRole("button", { name: `+ Schedule interview for ${who}` }).click();
    await settle(a, 1500);
    const c = cands();
    await c.getByLabel("Round (required)").selectOption({ label: round });
    await c.getByLabel("Date and time (IST, required)").fill(`${day}T${time}`);
    await c.getByLabel("Mode (required)").selectOption({ label: "Online" });
    await c.getByLabel("Platform").selectOption({ label: "Google Meet" });
    await c.getByLabel("Meeting link").fill("https://meet.google.com/docs-abcd-efg");
    const iv = c.getByRole("combobox", { name: "Interviewer" });
    if (await iv.count()) {
      await iv.click(); await iv.fill("Docs Interviewer"); await settle(a, 1500);
      const opts = await a.getByRole("option").allInnerTexts();
      console.log("VERIFY HIRE-006 interviewer options:", JSON.stringify(opts));
      await a.getByRole("option", { name: /Docs Interviewer/ }).first().click();
    } else await c.getByLabel("Interviewer").fill("Docs Interviewer");
    await c.getByLabel("Company contact").selectOption({ label: contact });
    await c.getByLabel("Duration").selectOption({ label: "1 h" });
    await c.getByLabel("Instructions").fill("Join 5 minutes early with your camera on. The round covers Python, FastAPI and SQL.");
    await c.getByLabel("Notify the candidate").check();
    if (shot) await shoot(a, H, shot, { root, element: c });
    await c.getByRole("button", { name: "Schedule interview", exact: true }).click();
    await settle(a, 3000);
    await say(a, `HIRE-006 scheduled ${who}`);
  }

  // ===== HIRE-006 schedule =====
  await step("HIRE-006 kiran", async () => {
    await schedule("Docs Candidate Kiran", "Technical Round", plusDays(1), "11:00", "16-schedule-interview.png", "Docs Rahul Hiring Manager");
    console.log("VERIFY HIRE-006 kiran panel:", await text(cands()));
  });
  await step("HIRE-006 nisha", async () => {
    await open();
    await cands().getByRole("button", { name: "Confirm review of Docs Candidate Nisha" }).click();
    await settle(a, 2500);
    await say(a, "HIRE-006 nisha review confirmed");
    await schedule("Docs Candidate Nisha", "HR Round", plusDays(1), "15:00", null, "Docs Priya HR Lead");
    await open();
    await cands().getByRole("button", { name: "Interviews of Docs Candidate Kiran" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-006 kiran interviews:", await text(cands()));
    console.log("VERIFY HIRE-006 controls:", await ctrls(cands()));
    await shoot(a, H, "17-interview-scheduled.png", { root, element: cands() });
  });

  // ===== HIRE-006 interview panel =====
  await step("HIRE-006 panel", async () => {
    for (const code of ["INT-000002", "INT-000003"]) {
      await a.goto("/recruiter/interviews");
      await settle(a, 3500);
      const card = a.locator("main article, main li, main .card").filter({ hasText: code }).first();
      await card.getByRole("button", { name: `Assign interviewers for ${code}` }).click();
      await settle(a, 1500);
      console.log(`VERIFY HIRE-006 panel fields ${code}:`, JSON.stringify(await fields(card)));
      const box = card.getByRole("combobox").first();
      if (await box.count()) { await box.click(); await box.fill("Docs Interviewer"); await settle(a, 1500); await a.getByRole("option", { name: /Docs Interviewer/ }).first().click(); await settle(a, 500); }
      else { for (const cb of await card.getByRole("checkbox", { name: /Docs Interviewer/ }).all()) await cb.check(); }
      if (code === "INT-000002") await shoot(a, H, "17b-assign-panel.png", { root, element: card });
      await card.getByRole("button", { name: /^(Save|Assign|Add)/ }).last().click();
      await settle(a, 2500);
      await say(a, `HIRE-006 panel ${code}`);
      console.log(`VERIFY HIRE-006 panel after ${code}:`, (await text(card)).slice(-500));
    }
  });

  // ===== HIRE-007 interviews list, reschedule =====
  await step("HIRE-007", async () => {
    await a.goto("/recruiter/interviews");
    await settle(a, 3500);
    console.log("VERIFY HIRE-007 list:", await text(a.locator("main")));
    console.log("VERIFY HIRE-007 controls:", await ctrls(a.locator("main")));
    await shoot(a, H, "18-interviews-list.png", { root });
    const card = a.locator("main article, main li, main .card").filter({ hasText: "Docs Candidate Nisha" }).first();
    const btn = card.getByRole("button", { name: /Reschedule/ }).first();
    await btn.click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-007 reschedule fields:", JSON.stringify(await fields(card)));
    const dt = card.locator('input[type="datetime-local"]').first();
    await dt.fill(`${plusDays(1)}T16:00`);
    const reason = card.locator("textarea, input[type=text]").first();
    if (await reason.count()) await reason.fill("Docs Priya asked to move it by an hour.");
    await shoot(a, H, "19-reschedule.png", { root, element: card });
    await card.getByRole("button", { name: /^(Save|Reschedule|Confirm)/ }).last().click();
    await settle(a, 3000);
    await say(a, "HIRE-007 rescheduled");
    console.log("VERIFY HIRE-007 after:", await text(card));
  });
  await a.context().close();

  // ===== HIRE-009 automation (Team Lead) =====
  const l = await as(browser, "lead");
  await step("HIRE-009", async () => {
    await l.goto("/recruiter/interviews");
    await settle(l, 3500);
    const au = sec(l, "Interview automation");
    await au.getByLabel("First reminder (hours before)").fill("24");
    await au.getByLabel("Second reminder (hours before)").fill("2");
    await au.getByLabel("Chase client feedback after (hours)").fill("24");
    await au.getByLabel("Escalate to Team Lead after (hours)").fill("24");
    await au.getByLabel("Reminder message").selectOption({ label: "Interview confirmation" });
    await shoot(l, H, "20-interview-automation.png", { root, element: au });
    await au.getByRole("button", { name: "Save automation" }).click();
    await settle(l, 2500);
    await say(l, "HIRE-009 saved");
    await shoot(l, H, "21-team-interviews.png", { root });
    console.log("VERIFY HIRE-009 team list:", (await text(l.locator("main"))).slice(-1200));
  });
  await l.context().close();

  // ===== INT-001 interviewer dashboard (upcoming) =====
  const iv = await as(browser, "int");
  await step("INT-001", async () => {
    await iv.goto("/it/interviewer/dashboard");
    await settle(iv, 3500);
    console.log("VERIFY INT-001:", await text(iv.locator("main")));
    console.log("VERIFY INT-001 controls:", await ctrls(iv.locator("main")));
    await shoot(iv, "interviewer", "01-my-interviews-upcoming.png", { root });
  });
  await iv.context().close();

  // ===== CAND-007 Nisha's upcoming interview =====
  const nctx = await browser.newContext();
  await noPrefetch(nctx);
  const n = await nctx.newPage();
  await n.goto("/it/login");
  await n.fill("#login-email", "docs.cand.nisha@example.com");
  await n.fill("#login-password", process.env.DOCS_TEST_PASSWORD!);
  await n.click("button:has-text('Sign in securely')");
  await n.waitForURL(/\/it\/careers\/portal/);
  await step("CAND-007 upcoming", async () => {
    await n.goto("/it/careers/portal/interviews");
    await settle(n, 3500);
    console.log("VERIFY CAND-007 interviews:", await text(n.locator("main")));
    await shoot(n, "candidate-portal", "15-interviews-upcoming.png", { root });
  });
  await nctx.close();
});
