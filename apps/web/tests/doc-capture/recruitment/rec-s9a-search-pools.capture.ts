import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S9 (docs/recruitment-crm/documentation-plan.md): DOC-REC-SRCH-001..005, HR-006. Runs after rec-s8e.
// Recruiter A searches, saves a shared search, shortlists Docs Candidate Kiran into REQ-000005 (used by S10) and assigns a task;
// Share selected is not used here (profile sharing is documented with the hiring flow). The Team Lead exports; HR reads only.
const root = REC_ROOT;
const R = "search";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const fields = (l: Locator) => l.evaluate((el) => [...el.querySelectorAll("input, select, textarea")].map((e) => {
  const f = e as HTMLInputElement;
  const lab = (f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.textContent?.trim()) || f.getAttribute("aria-label") || f.closest("label")?.textContent?.trim() || f.name;
  const o = f.tagName === "SELECT" ? " [" + [...(f as unknown as HTMLSelectElement).options].map((x) => x.text).join("|") + "]" : "";
  return `${f.type} "${(lab ?? "").slice(0, 60)}"${o}`;
}));
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}
async function as(browser: Browser, who: "a" | "lead" | "hr") {
  const ctx = await browser.newContext({ acceptDownloads: true });
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  p.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  if (who === "lead") await signIn(p, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  else if (who === "a") await signIn(p, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  else await signIn(p, "docs.rec.hr@example.test", "test", /\/it\/hr\/dashboard|\/recruiter/, "/it/login");
  return p;
}
const results = (p: Page) => p.locator("main").getByText(/candidates? found/).first().locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function chip(p: Page, label: string, value: string) {
  const f = p.getByLabel(label);
  await f.fill(value);
  await settle(p, 1200);
  await f.press("Enter");
  await settle(p, 600);
}

test("Recruitment CRM S9 search and pools", async ({ browser }) => {
  test.setTimeout(1_500_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const a = await as(browser, "a");
  const m = a.locator("main");

  // ===== SRCH-001 skills search =====
  await step("SRCH-001", async () => {
    await a.goto("/recruiter/find-candidates");
    await settle(a, 3000);
    await shoot(a, R, "01-find-candidates.png", { root });
    await chip(a, "Must have all of these skills", "Python");
    await chip(a, "Nice to have (ranks, never excludes)", "Docs FastAPI");
    await shoot(a, R, "02-skills-entered.png", { root, element: m.locator('form[role="search"]').first() });
    await m.getByRole("button", { name: "Search candidates" }).click();
    await settle(a, 3500);
    console.log("VERIFY SRCH-001 url:", a.url());
    console.log("VERIFY SRCH-001 results:", (await text(results(a))).slice(0, 2000));
    await shoot(a, R, "03-results.png", { root, element: results(a) });
  });

  // ===== SRCH-002 refine + resume search =====
  await step("SRCH-002 refine", async () => {
    const sort = m.getByLabel("Sort by");
    console.log("VERIFY SRCH-002 sort:", JSON.stringify(await sort.locator("option").allInnerTexts()));
    await sort.selectOption({ label: "Most matching skills" });
    await settle(a, 2500);
    await m.getByRole("button", { name: /^1–3 years/ }).first().click();
    await settle(a, 2500);
    console.log("VERIFY SRCH-002 refined url:", a.url());
    console.log("VERIFY SRCH-002 active filters:", await text(m.getByRole("list", { name: "Active filters" })));
    await shoot(a, R, "04-refined.png", { root });
  });
  await step("SRCH-002 resume", async () => {
    await a.goto("/recruiter/find-candidates");
    await settle(a, 3000);
    await a.getByLabel("Resume search").fill('"REST APIs" FastAPI');
    await m.getByRole("button", { name: "Search candidates" }).click();
    await settle(a, 3500);
    console.log("VERIFY SRCH-002 resume:", (await text(results(a))).slice(0, 1500));
    await shoot(a, R, "05-resume-search.png", { root, element: results(a) });
  });

  // ===== SRCH-003 saved search (shared with the team) =====
  await step("SRCH-003 save", async () => {
    await a.goto("/recruiter/find-candidates");
    await settle(a, 3000);
    await chip(a, "Must have all of these skills", "Python");
    await chip(a, "Nice to have (ranks, never excludes)", "Docs FastAPI");
    await a.getByLabel("City").fill("Hyderabad");
    await m.getByRole("button", { name: "Search candidates" }).click();
    await settle(a, 3500);
    await m.getByRole("button", { name: "Save this search" }).click();
    await settle(a, 1000);
    await a.getByLabel("Saved search name").fill("Docs Python + FastAPI, Hyderabad");
    await a.getByLabel("Share with the team").check();
    const ss = m.getByRole("heading", { name: "Saved searches" }).locator("xpath=ancestor::section[1]");
    await shoot(a, R, "06-save-search.png", { root, element: ss });
    await a.getByRole("form", { name: "Save this search" }).getByRole("button", { name: "Save", exact: true }).click();
    await settle(a, 2500);
    await say(a, "SRCH-003 saved");
    await a.goto("/recruiter/find-candidates");
    await settle(a, 3000);
    console.log("VERIFY SRCH-003 options:", JSON.stringify(await a.getByLabel("Load a saved search").locator("option, optgroup").evaluateAll((els) => els.map((e) => (e.tagName === "OPTGROUP" ? `[${(e as HTMLOptGroupElement).label}]` : e.textContent)))));
    await a.getByLabel("Load a saved search").selectOption({ label: "Docs Python + FastAPI, Hyderabad" });
    await settle(a, 3500);
    console.log("VERIFY SRCH-003 loaded:", a.url());
    await shoot(a, R, "07-saved-search-loaded.png", { root, element: ss });
  });

  // ===== SRCH-004 bulk: shortlist into REQ-000005, assign task, share (opened only) =====
  await step("SRCH-004 shortlist", async () => {
    const reqSel = m.getByRole("combobox", { name: "Shortlist into requirement" });
    await reqSel.click();
    await reqSel.fill("Docs Python");
    await settle(a, 1500);
    console.log("VERIFY SRCH-004 requirements:", JSON.stringify(await a.getByRole("option").allInnerTexts()));
    await a.getByRole("option", { name: /Docs Python Developer/ }).first().click();
    await settle(a, 2000);
    const row = m.locator("input[type=checkbox]").filter({ has: a.locator("xpath=self::*") });
    const kiranBox = m.getByRole("checkbox", { name: /Docs Candidate Kiran/ }).or(m.getByLabel(/Select Docs Candidate Kiran/)).first();
    if (await kiranBox.count()) await kiranBox.check();
    else await m.locator("article input[type=checkbox], li input[type=checkbox]").first().check();
    void row;
    await settle(a, 1000);
    await shoot(a, R, "08-selected.png", { root, element: m.getByRole("group", { name: "Selected candidates" }).locator("xpath=..") });
    await m.getByRole("button", { name: /^Shortlist selected/ }).click();
    await settle(a, 3000);
    await say(a, "SRCH-004 shortlisted");
    console.log("VERIFY SRCH-004 card:", (await text(results(a))).slice(-900));
    await shoot(a, R, "09-shortlisted.png", { root, element: results(a) });
  });
  await step("SRCH-004 task", async () => {
    const kiranBox = m.getByRole("checkbox", { name: /Docs Candidate Kiran/ }).or(m.getByLabel(/Select Docs Candidate Kiran/)).first();
    if (await kiranBox.count() && !(await kiranBox.isChecked())) await kiranBox.check();
    await m.getByRole("button", { name: /^Assign task/ }).click();
    await settle(a, 1500);
    const grp = m.getByRole("group", { name: "Selected candidates" }).locator("xpath=..");
    console.log("VERIFY SRCH-004 task fields:", JSON.stringify(await fields(grp)));
    const sel = async (re: RegExp, label: string) => { const f = grp.getByLabel(re).first(); if (await f.count()) await f.selectOption({ label }).catch(async () => f.selectOption({ index: 1 })); };
    await sel(/^Task type/, "Follow-up");
    await grp.getByLabel("Title").fill("Confirm interest in Docs Acme Python Developer");
    await grp.getByLabel("Due (IST)").fill(new Date(Date.now() + 5.5 * 3600_000 + 86_400_000).toISOString().slice(0, 10) + "T12:00");
    const who = grp.getByRole("combobox", { name: "Assign to" });
    await who.click();
    await who.fill("Docs Recruiter A");
    await settle(a, 1500);
    await a.getByRole("option", { name: /Docs Recruiter A/ }).first().click();
    await settle(a, 500);
    await shoot(a, R, "10-assign-task.png", { root, element: grp });
    await grp.getByRole("button", { name: /^Create \d+ task/ }).click();
    await settle(a, 3000);
    await say(a, "SRCH-004 task");
    console.log("VERIFY SRCH-004 task after:", (await text(grp)).slice(0, 600));
  });
  await a.context().close();

  // ===== SRCH-003 export (Team Lead) =====
  const l = await as(browser, "lead");
  await step("SRCH-003 export", async () => {
    await l.goto("/recruiter/find-candidates");
    await settle(l, 3000);
    console.log("VERIFY SRCH-003 lead options:", JSON.stringify(await l.getByLabel("Load a saved search").locator("option").allInnerTexts()));
    await l.getByLabel("Load a saved search").selectOption({ label: "Docs Python + FastAPI, Hyderabad — Docs Recruiter A" });
    await settle(l, 3500);
    const bar = l.locator("main").getByRole("button", { name: "Export CSV" });
    console.log("VERIFY SRCH-003 export buttons:", JSON.stringify(await l.locator("main button").filter({ hasText: /Export/ }).allInnerTexts()));
    await shoot(l, R, "12-export.png", { root, element: results(l) });
    const dl = l.waitForEvent("download", { timeout: 15000 });
    await bar.click();
    const d = await dl;
    console.log("VERIFY SRCH-003 download:", d.suggestedFilename());
    const p = await d.path();
    console.log("VERIFY SRCH-003 csv head:", readFileSync(p!, "utf8").split("\n").slice(0, 2).join(" || ").slice(0, 600));
  });

  // ===== SRCH-005 pools (Team Lead) =====
  await step("SRCH-005", async () => {
    await l.goto("/recruiter/pools");
    await settle(l, 3000);
    console.log("VERIFY SRCH-005 pools:", await text(l.locator("main")));
    await shoot(l, R, "13-talent-pools.png", { root });
    await l.getByRole("link", { name: /Experienced Professionals/ }).first().click();
    await settle(l, 3000);
    console.log("VERIFY SRCH-005 pool:", (await text(l.locator("main"))).slice(0, 1500));
    await shoot(l, R, "14-pool-page.png", { root });
    console.log("VERIFY SRCH-005 pool controls:", JSON.stringify([...new Set((await l.locator("main button, main a").allInnerTexts()).map((b) => b.trim()).filter(Boolean))].slice(0, 12)));
    await l.goto("/recruiter/pools");
    await settle(l, 3000);
    await l.locator("main").getByRole("button", { name: "+ New pool" }).or(l.locator("main").getByRole("link", { name: "+ New pool" })).first().click();
    await settle(l, 2500);
    const form = l.locator("main form").first();
    console.log("VERIFY SRCH-005 new pool fields:", JSON.stringify(await fields(form)));
    console.log("VERIFY SRCH-005 new pool text:", (await text(form)).slice(0, 1200));
    const fillIf = async (re: RegExp, v: string) => { const f = form.getByLabel(re).first(); if (await f.count()) await f.fill(v); };
    await fillIf(/^(Pool )?name/i, "Docs FastAPI developers");
    await fillIf(/^Description/i, "Docs: candidates with FastAPI");
    const skill = form.getByRole("combobox", { name: /skill/i }).first();
    if (await skill.count()) { await skill.click(); await skill.fill("Docs Fast"); await settle(l, 1500); await l.getByRole("option", { name: /^Docs FastAPI/ }).first().click(); await settle(l, 500); }
    else { const t = form.getByLabel(/skill/i).first(); if (await t.count()) { await t.fill("Docs FastAPI"); await t.press("Enter"); } }
    await shoot(l, R, "19-new-pool.png", { root, element: form });
    await form.getByRole("button", { name: /^(Create|Save|Add)/ }).last().click();
    await settle(l, 3000);
    await say(l, "SRCH-005 new pool");
    console.log("VERIFY SRCH-005 after:", l.url(), (await text(l.locator("main"))).slice(0, 900));
    await shoot(l, R, "20-new-pool-created.png", { root });
  });
  await l.context().close();

  // ===== HR-006 read only =====
  const h = await as(browser, "hr");
  await step("HR-006", async () => {
    await h.goto("/recruiter/candidates");
    await settle(h, 3000);
    await shoot(h, R, "15-hr-candidates.png", { root });
    await h.goto(`/recruiter/candidates/${ids.candidates.kiran}`);
    await settle(h, 3500);
    console.log("VERIFY HR-006 page:", (await text(h.locator("main"))).slice(0, 1500));
    console.log("VERIFY HR-006 buttons:", JSON.stringify([...new Set((await h.locator("main button, main a").allInnerTexts()).map((b) => b.trim()).filter(Boolean))]));
    await shoot(h, R, "16-hr-candidate-page.png", { root });
    await h.goto("/recruiter/find-candidates");
    await settle(h, 3000);
    await chip(h, "Must have all of these skills", "Python");
    await h.locator("main").getByRole("button", { name: "Search candidates" }).click();
    await settle(h, 3500);
    console.log("VERIFY HR-006 search:", (await text(results(h))).slice(0, 1200));
    console.log("VERIFY HR-006 search buttons:", JSON.stringify([...new Set((await results(h).locator("button, a").allInnerTexts()).map((b) => b.trim()).filter(Boolean))]));
    await shoot(h, R, "17-hr-find-candidates.png", { root, element: results(h) });
    await h.goto("/recruiter/pools");
    await settle(h, 3000);
    await shoot(h, R, "18-hr-pools.png", { root });
  });
  await h.context().close();
});
