import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S10 (docs/recruitment-crm/documentation-plan.md): DOC-REC-HIRE-001..005, CAND-005/006. Runs after rec-s9a.
// Docs Candidate Nisha applies to REQ-000005 from her portal; Recruiter A works both candidates on REQ-000005: status, screening form
// and checklist, match weights, shares Docs Candidate Kiran (named, by email) with Docs Priya HR Lead and records the client's response.
const root = REC_ROOT;
const H = "hiring";
const P = "candidate-portal";
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
async function nisha(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  await p.goto("/it/login");
  await p.fill("#login-email", "docs.cand.nisha@example.com");
  await p.fill("#login-password", process.env.DOCS_TEST_PASSWORD!);
  await p.click("button:has-text('Sign in securely')");
  await p.waitForURL(/\/it\/careers\/portal/);
  return p;
}
const plusDays = (n: number) => new Date(Date.now() + 5.5 * 3600_000 + n * 86_400_000).toISOString().slice(0, 10);

test("Recruitment CRM S10 hiring A", async ({ browser }) => {
  test.setTimeout(1_500_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));

  // ===== CAND-005 Nisha applies from the portal =====
  const n = await nisha(browser);
  await step("CAND-005", async () => {
    await n.goto("/it/careers/portal/jobs");
    await settle(n, 3000);
    await shoot(n, P, "11-jobs-recommended.png", { root });
    await n.getByRole("link", { name: /All open jobs/ }).or(n.getByRole("button", { name: /All open jobs/ })).first().click();
    await settle(n, 3000);
    const card = n.locator("main article, main li, main .card").filter({ hasText: "Docs Python Developer" }).first();
    await shoot(n, P, "12-all-open-jobs.png", { root });
    await card.getByRole("button", { name: "Apply" }).click();
    await settle(n, 3000);
    await say(n, "CAND-005 applied");
    console.log("VERIFY CAND-005 card:", await text(card));
    await shoot(n, P, "13-applied.png", { root, element: card });
  });
  await n.context().close();

  // ===== Recruiter A on REQ-000005 =====
  const actx = await browser.newContext();
  await noPrefetch(actx);
  const a = await actx.newPage();
  a.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  const url = `/recruiter/requirements/${ids.requirements.python}`;
  const open = async () => { await a.goto(url); await settle(a, 3500); };
  const cands = () => sec(a, /^Candidates \(/);

  // HIRE-001 candidates, status, history
  await step("HIRE-001", async () => {
    await open();
    console.log("VERIFY HIRE-001 card:", await text(cands()));
    await shoot(a, H, "01-candidates.png", { root, element: cands() });
    await cands().getByRole("button", { name: "Change status of Docs Candidate Nisha" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-001 nisha statuses:", JSON.stringify(await cands().getByLabel("New status").locator("option").allInnerTexts()));
    await cands().getByLabel("New status").selectOption({ label: "Screened" });
    await cands().getByLabel("Note (optional)").fill("Phone screen done: 1 year Django and FastAPI. Needs the skills added to her profile.");
    await shoot(a, H, "02-change-status.png", { root, element: cands() });
    await cands().getByRole("button", { name: "Save status" }).click();
    await settle(a, 2500);
    await say(a, "HIRE-001 nisha screened");
    await cands().getByRole("button", { name: "History of Docs Candidate Nisha" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-001 history:", await text(cands()));
    await shoot(a, H, "03-history.png", { root, element: cands() });
  });

  // HIRE-003 screening form and checklist
  await step("HIRE-003 form", async () => {
    await open();
    const sf = () => sec(a, "Screening form");
    await sf().getByRole("button", { name: "Show screening form" }).click();
    await settle(a, 1500);
    await sf().getByLabel("Template").selectOption({ label: "Docs Python developer screening" });
    await sf().getByRole("button", { name: "Create form" }).click();
    await settle(a, 3000);
    await say(a, "HIRE-003 form created");
    console.log("VERIFY HIRE-003 form:", await text(sf()));
    console.log("VERIFY HIRE-003 form controls:", await ctrls(sf()));
    await shoot(a, H, "04-screening-form.png", { root, element: sf() });
  });
  await step("HIRE-003 session", async () => {
    await open();
    await cands().getByRole("button", { name: "Screening of Docs Candidate Kiran" }).click();
    await settle(a, 2000);
    console.log("VERIFY HIRE-003 screening panel:", await text(cands()));
    console.log("VERIFY HIRE-003 screening controls:", await ctrls(cands()));
    const start = cands().getByRole("button", { name: "Record a session for Docs Candidate Kiran" });
    if (await start.count()) {
      await start.click();
      await settle(a, 2000);
      console.log("VERIFY HIRE-003 session fields:", JSON.stringify(await fields(cands())));
      const c = cands();
      await c.getByLabel("How many years of Python have you used in paid work?", { exact: true }).fill("2");
      await c.getByLabel(/^Score for How many years/).selectOption({ label: "4 / 5" });
      await c.getByLabel("Docs: Have you built REST APIs with Python (Django or FastAPI)?", { exact: true }).selectOption({ label: "Yes" });
      await c.getByLabel(/^Score for Docs: Have you built/).selectOption({ label: "5 / 5" });
      await c.getByLabel(/^What is your notice period/).fill("30 days; already in Hyderabad.");
      await c.getByLabel(/^Score for What is your notice period/).selectOption({ label: "4 / 5" });
      await c.getByLabel("Recommendation").selectOption({ label: "Pass" });
      await c.getByLabel("Notes (internal)").fill("Built REST APIs with FastAPI at Docs Orbit Softech; clear answers.");
      console.log("VERIFY HIRE-003 session buttons:", await ctrls(c));
      await shoot(a, H, "05-screening-session.png", { root, element: c });
      await c.getByRole("button", { name: /session/i }).filter({ hasNotText: /^Record a session/ }).first().click();
      await settle(a, 2500);
      await say(a, "HIRE-003 session saved");
      console.log("VERIFY HIRE-003 after session:", await text(cands()));
    }
  });
  await step("HIRE-003 checklist", async () => {
    await open();
    await cands().getByRole("button", { name: "Screening of Docs Candidate Kiran" }).click();
    await settle(a, 2000);
    const c = cands();
    for (const v of ["Qualification verified", "Experience verified", "Skills verified"]) await c.getByLabel(v).check();
    await c.getByLabel("Expected salary (per year)").fill("800000");
    await c.getByLabel("Notice period (days)").fill("30");
    await c.getByLabel("Location preference").fill("Hyderabad");
    await c.getByLabel("Availability").fill("Can join in 30 days");
    await c.getByLabel("Communication skills").selectOption({ label: "4 / 5" });
    await c.getByLabel("Technical screening").selectOption({ label: "4 / 5" });
    await c.getByLabel("Willing to relocate").selectOption({ label: "Yes" });
    await c.getByLabel("Result").selectOption({ label: "Shortlisted" });
    await c.getByLabel("Recruiter remarks").fill("Strong FastAPI and SQL. Good communication. Recommend sharing with Docs Acme.");
    await shoot(a, H, "06-screening-checklist.png", { root, element: c });
    await c.getByRole("button", { name: "Save screening" }).click();
    await settle(a, 2500);
    await say(a, "HIRE-003 checklist");
    console.log("VERIFY HIRE-003 checklist after:", await text(cands()));
  });

  // HIRE-004 share Kiran with Docs Priya by email
  await step("HIRE-004", async () => {
    await open();
    await cands().getByRole("checkbox", { name: "Select Docs Candidate Kiran to share" }).check();
    await cands().getByRole("button", { name: /^Share selected/ }).click();
    await settle(a, 2000);
    const f = a.getByRole("form", { name: /^Share \d+ profile/ });
    await f.getByRole("radio", { name: /^Email/ }).check();
    await f.getByRole("combobox", { name: "Contact" }).selectOption({ label: "Docs Priya HR Lead — Talent Acquisition Lead" });
    await f.getByRole("radio", { name: /^Named/ }).check();
    await f.getByLabel("The candidates agreed to this submission").check();
    await f.getByLabel("How and when they agreed (required)").fill("Phone call with Docs Recruiter A on 19 Nov 2026");
    await f.getByLabel(/The candidates confirmed their interest/).check();
    await f.getByLabel("Internal note (optional, never sent)").fill("First profile for REQ-000005.");
    await shoot(a, H, "09-share-form.png", { root, element: f });
    await f.getByRole("button", { name: /^Share \d+ profile/ }).click();
    await settle(a, 3500);
    await say(a, "HIRE-004 shared");
    console.log("VERIFY HIRE-004 candidates:", await text(cands()));
  });

  // HIRE-005 shared profiles and client response
  await step("HIRE-005", async () => {
    await open();
    const sp = () => sec(a, /^Shared profiles/);
    console.log("VERIFY HIRE-005 card:", await text(sp()));
    console.log("VERIFY HIRE-005 controls:", await ctrls(sp()));
    await shoot(a, H, "10-shared-profiles.png", { root, element: sp() });
    const rec = sp().getByRole("button", { name: "Update submission for Docs Candidate Kiran" });
    if (await rec.count()) {
      await rec.click();
      await settle(a, 1500);
      console.log("VERIFY HIRE-005 response fields:", JSON.stringify(await fields(sp())));
      for (const sel of await sp().locator("select").all()) {
        const opts = await sel.locator("option").allInnerTexts();
        console.log("VERIFY HIRE-005 select:", await sel.getAttribute("aria-label") ?? "", JSON.stringify(opts));
        const pickOpt = opts.find((o) => /shortlisted|interested|interview/i.test(o));
        if (pickOpt) await sel.selectOption({ label: pickOpt });
      }
      await sp().getByLabel("The client acknowledged receiving this profile").check();
      const note = sp().locator("textarea").first();
      if (await note.count()) await note.fill("Docs Priya: profile looks good, please set up a technical round.");
      await shoot(a, H, "11-client-response.png", { root, element: sp() });
      console.log("VERIFY HIRE-005 response buttons:", await ctrls(sp()));
      await sp().getByRole("button", { name: /^(Save|Record)/ }).first().click();
      await settle(a, 2500);
      await say(a, "HIRE-005 response");
      console.log("VERIFY HIRE-005 after:", await text(sp()));
      await shoot(a, H, "12-response-recorded.png", { root, element: sp() });
    }
    await open();
    console.log("VERIFY HIRE-005 candidates after:", await text(cands()));
    await shoot(a, H, "13-candidates-after.png", { root, element: cands() });
  });
  // HIRE-002 matching and weights
  await step("HIRE-002", async () => {
    await open();
    const mc = () => sec(a, /^Matching candidates/);
    await shoot(a, H, "07-matching.png", { root, element: mc() });
    await mc().getByRole("button", { name: "Adjust weights" }).click();
    await settle(a, 1500);
    await mc().getByLabel("Weight of Python (required)").fill("10");
    await mc().getByLabel("Minimum level of Python (required)").selectOption({ label: "Intermediate" });
    await shoot(a, H, "08-adjust-weights.png", { root, element: mc() });
    await mc().getByRole("button", { name: "Save weights" }).click();
    await settle(a, 3000);
    await say(a, "HIRE-002 weights");
    console.log("VERIFY HIRE-002 after:", (await text(mc())).slice(0, 900));
    await shoot(a, H, "14-weights-saved.png", { root, element: mc() });
    await open();
    console.log("VERIFY HIRE-002 review:", (await text(cands())).slice(0, 700));
    await shoot(a, H, "15-needs-review.png", { root, element: cands() });
    await cands().getByRole("button", { name: "Confirm review of Docs Candidate Kiran" }).click();
    await settle(a, 2500);
    await say(a, "HIRE-002 confirmed");
    console.log("VERIFY HIRE-002 after confirm:", (await text(cands())).slice(0, 700));
  });

  await actx.close();

  // ===== CAND-006 Nisha's applications =====
  const n2 = await nisha(browser);
  await step("CAND-006", async () => {
    await n2.goto("/it/careers/portal/applications");
    await settle(n2, 3500);
    console.log("VERIFY CAND-006 page:", await text(n2.locator("main")));
    await shoot(n2, P, "14-my-applications.png", { root });
  });
  await n2.context().close();
  void plusDays;
});
