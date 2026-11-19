import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S11b (docs/recruitment-crm/documentation-plan.md): DOC-REC-INT-001/002, HIRE-008, HRM-002, CAND-007, ADM-006 (result
// release, viewed only), HR-001..003. Runs after rec-s11a and the s11-backdate.sql step (INT-000002/3 moved into the past).
// Docs Interviewer gives feedback (Kiran: hire; Nisha: no hire); Recruiter A records the outcomes; the HR Manager publishes the results.
const root = REC_ROOT;
const H = "hiring";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
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
async function as(browser: Browser, who: "a" | "hrm" | "int" | "hr" | "sa") {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  p.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  if (who === "a") await signIn(p, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  else if (who === "sa") await signIn(p, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  else await signIn(p, `docs.rec.${who === "int" ? "interviewer" : who}@example.test`, "test", /\/it\/(hr|hr-manager|interviewer)\/dashboard/, "/it/login");
  return p;
}
const card = (p: Page, txt: string) => p.locator("main article, main li, main .card").filter({ hasText: txt }).first();
// Pick, in every select of `box`, the first option matching `want` (by label text); log the options.
async function pickAll(box: Locator, want: RegExp, tag: string) {
  for (const sel of await box.locator("select").all()) {
    const lab = await sel.evaluate((e) => (e.id && document.querySelector(`label[for="${CSS.escape(e.id)}"]`)?.textContent?.trim()) || e.getAttribute("aria-label") || "");
    const opts = await sel.locator("option").allInnerTexts();
    console.log(`VERIFY ${tag} select "${lab}":`, JSON.stringify(opts));
    const hit = opts.find((o) => want.test(o)) ?? opts.find((o) => /5 \/ 5|4 \/ 5|Strong|Good/.test(o));
    if (hit) await sel.selectOption({ label: hit });
  }
}

test("Recruitment CRM S11b feedback and results", async ({ browser }) => {
  test.setTimeout(1_500_000);

  // ===== INT-001/002 interviewer feedback =====
  const iv = await as(browser, "int");
  for (const [code, who, score, rec, note] of [
    ["INT-000002", "Docs Candidate Kiran", "5 / 5", "Strongly recommend", "Clear FastAPI design and clean SQL. Recommend for the role."],
    ["INT-000003", "Docs Candidate Nisha", "2 / 5", "Do not recommend", "Good attitude but not enough Python experience for this role yet."],
  ] as const) {
    await step(`INT-002 ${who}`, async () => {
      await iv.goto("/it/interviewer/dashboard");
      await settle(iv, 3000);
      await iv.locator("main").getByRole("button", { name: /^Past/ }).or(iv.locator("main").getByRole("link", { name: /^Past/ })).first().click();
      await settle(iv, 2500);
      if (code === "INT-000002") { console.log("VERIFY INT-001 past:", await text(iv.locator("main"))); await shoot(iv, "interviewer", "01b-my-interviews-past.png", { root }); }
      await iv.locator("main").getByRole("button", { name: `Submit feedback for ${code}` }).click();
      await settle(iv, 1500);
      const f = iv.locator("main form").filter({ has: iv.getByRole("button", { name: "Save feedback" }) }).first();
      await f.getByRole("radio", { name: "Attended" }).check();
      await f.getByLabel("Score (required)").selectOption({ label: score });
      await f.getByLabel("Recommendation (required)").selectOption({ label: rec });
      await f.getByLabel("Notes").fill(note);
      if (code === "INT-000002") await shoot(iv, "interviewer", "02-feedback-form.png", { root, element: f });
      await f.getByRole("button", { name: "Save feedback" }).click();
      await settle(iv, 3000);
      await say(iv, `INT-002 ${who}`);
      const c = card(iv, code);
      console.log(`VERIFY INT-002 after ${who}:`, (await text(c)).slice(0, 900));
      if (code === "INT-000002") await shoot(iv, "interviewer", "03-feedback-submitted.png", { root, element: c });
    });
  }
  await iv.context().close();

  // ===== HIRE-008 recruiter records the outcome =====
  const a = await as(browser, "a");
  for (const [code, final, note] of [
    ["INT-000002", "Selected", "Cleared the technical round; Docs Rahul wants to make an offer."],
    ["INT-000003", "Rejected", "Not taken forward after the HR round."],
  ] as const) {
    await step(`HIRE-008 ${code}`, async () => {
      for (const target of ["Completed", final]) {
        await a.goto("/recruiter/interviews");
        await settle(a, 3000);
        await a.locator("main").getByRole("button", { name: /^Awaiting update/ }).or(a.locator("main").getByRole("link", { name: /^Awaiting update/ })).first().click();
        await settle(a, 2500);
        if (code === "INT-000002" && target === "Completed") { console.log("VERIFY HIRE-008 awaiting:", (await text(a.locator("main"))).slice(0, 1600)); await shoot(a, H, "22-awaiting-update.png", { root }); }
        const c = card(a, code);
        await c.getByRole("button", { name: `Change status of ${code}` }).click();
        await settle(a, 1500);
        const sel = c.getByLabel("New status (required)");
        console.log(`VERIFY HIRE-008 ${code} options before ${target}:`, JSON.stringify(await sel.locator("option").allInnerTexts()));
        await sel.selectOption({ label: target });
        await c.getByLabel("Note (optional)").fill(target === "Completed" ? "Interview held on time." : note);
        console.log(`VERIFY HIRE-008 ${code} buttons:`, await ctrls(c));
        if (code === "INT-000002") await shoot(a, H, target === "Completed" ? "23-interview-completed.png" : "23b-interview-selected.png", { root, element: c });
        await c.getByRole("button", { name: /^Save/ }).first().click();
        await settle(a, 3000);
        await say(a, `HIRE-008 ${code} ${target}`);
        console.log(`VERIFY HIRE-008 after ${code} ${target}:`, (await text(c).catch(() => "(moved to Closed)")).slice(0, 1000));
      }
    });
  }
  await step("HIRE-008 closed", async () => {
    await a.goto("/recruiter/interviews");
    await settle(a, 3000);
    await a.locator("main").getByRole("button", { name: /^Closed/ }).or(a.locator("main").getByRole("link", { name: /^Closed/ })).first().click();
    await settle(a, 2500);
    console.log("VERIFY HIRE-008 closed:", (await text(a.locator("main"))).slice(0, 1600));
    await shoot(a, H, "24-interviews-closed.png", { root });
  });
  await a.context().close();

  // ===== HRM-002 result approvals =====
  const m = await as(browser, "hrm");
  await step("HRM-002", async () => {
    await m.goto("/it/hr-manager/results");
    await settle(m, 3500);
    console.log("VERIFY HRM-002 queue:", await text(m.locator("main")));
    console.log("VERIFY HRM-002 controls:", await ctrls(m.locator("main")));
    console.log("VERIFY HRM-002 fields:", JSON.stringify(await fields(m.locator("main"))));
    await shoot(m, "hr-manager", "04-result-approvals.png", { root });
    for (const who of ["Docs Candidate Nisha", "Docs Candidate Kiran"]) {
      const c = card(m, who);
      if (!(await c.count())) { console.log(`VERIFY HRM-002 no card for ${who}`); continue; }
      const ta = c.locator("textarea");
      if (await ta.count()) await ta.first().fill(who.endsWith("Nisha") ? "Thank you for interviewing with Docs Acme Technologies. We will not be taking your application forward this time." : "Congratulations, you have cleared the technical round with Docs Acme Technologies.");
      if (who.endsWith("Nisha")) await shoot(m, "hr-manager", "05-publish-result.png", { root, element: c });
      await c.getByRole("button", { name: /^(Publish|Approve)/ }).first().click();
      await settle(m, 3000);
      await say(m, `HRM-002 ${who}`);
    }
    await m.reload();
    await settle(m, 3000);
    await m.locator("main").getByRole("button", { name: /^Published/ }).or(m.locator("main").getByRole("link", { name: /^Published/ })).first().click().catch(() => undefined);
    await settle(m, 2000);
    console.log("VERIFY HRM-002 published:", await text(m.locator("main")));
    await shoot(m, "hr-manager", "06-results-published.png", { root });
  });
  await m.context().close();

  // ===== ADM-006 result release (Super Admin, viewed only) =====
  const sa = await as(browser, "sa");
  await step("ADM-006 release", async () => {
    await sa.goto("/it/hr-manager/results");
    await settle(sa, 3500);
    const box = sa.getByRole("heading", { name: "How results are released" }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");
    console.log("VERIFY ADM-006 release:", await text(box));
    await shoot(sa, "admin", "21-result-release.png", { root, element: box });
  });
  await sa.context().close();

  // ===== CAND-007 Nisha's interviews and results =====
  const nctx = await browser.newContext();
  await noPrefetch(nctx);
  const n = await nctx.newPage();
  await n.goto("/it/login");
  await n.fill("#login-email", "docs.cand.nisha@example.com");
  await n.fill("#login-password", process.env.DOCS_TEST_PASSWORD!);
  await n.click("button:has-text('Sign in securely')");
  await n.waitForURL(/\/it\/careers\/portal/);
  await step("CAND-007", async () => {
    await n.goto("/it/careers/portal/results");
    await settle(n, 3500);
    console.log("VERIFY CAND-007 results:", await text(n.locator("main")));
    await shoot(n, "candidate-portal", "16-my-results.png", { root });
    await n.goto("/it/careers/portal/interviews");
    await settle(n, 3000);
    console.log("VERIFY CAND-007 interviews:", await text(n.locator("main")));
    await shoot(n, "candidate-portal", "17-interviews-after.png", { root });
  });
  await nctx.close();

  // ===== HR-001..003 =====
  const hr = await as(browser, "hr");
  await step("HR-001..003", async () => {
    await hr.goto("/it/hr/job-requirements");
    await settle(hr, 3000);
    await shoot(hr, "hr", "01-job-requirements.png", { root });
    await hr.goto("/it/hr/shortlists");
    await settle(hr, 3000);
    await hr.getByLabel("Hiring requirement").selectOption({ label: "Docs Python Developer · Docs Acme Technologies · Requirement Received" }).catch(async () => hr.getByLabel("Hiring requirement").selectOption({ index: 1 }));
    await settle(hr, 3000);
    console.log("VERIFY HR-001 shortlist:", await text(hr.locator("main")));
    await shoot(hr, "hr", "02-shortlists.png", { root });
    await hr.goto("/it/hr/candidates");
    await settle(hr, 3000);
    await shoot(hr, "hr", "03-candidate-database.png", { root });
    await hr.goto("/it/hr/interviews");
    await settle(hr, 3000);
    console.log("VERIFY HR-002 interviews:", await text(hr.locator("main")));
    await shoot(hr, "hr", "04-interviews.png", { root });
    await hr.goto("/it/hr/reports");
    await settle(hr, 3000);
    console.log("VERIFY HR-003 reports:", (await text(hr.locator("main"))).slice(0, 600));
    await shoot(hr, "hr", "05-placement-reports.png", { root });
  });
  await hr.context().close();
});
