import { readFileSync } from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S11c (docs/recruitment-crm/documentation-plan.md): DOC-REC-HIRE-010. Runs after rec-s11b.
// Recruiter A marks Docs Candidate Kiran Selected (his Technical Round result is published) and records the offer. The offer CTC is the
// candidate's salary, not money EduSphere receives (R3 is about fees, invoices and payments).
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

test("Recruitment CRM S11c offer", async ({ browser }) => {
  test.setTimeout(900_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  a.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  const url = `/recruiter/requirements/${ids.requirements.python}`;
  const open = async () => { await a.goto(url); await settle(a, 3500); };
  const cands = () => sec(a, /^Candidates \(/);

  await step("selected", async () => {
    await open();
    console.log("VERIFY HIRE-010 before:", await text(cands()));
    await cands().getByRole("button", { name: "Change status of Docs Candidate Kiran" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-010 statuses:", JSON.stringify(await cands().getByLabel("New status").locator("option").allInnerTexts()));
    await cands().getByLabel("New status").selectOption({ label: "Selected" });
    await cands().getByLabel("Note (optional)").fill("Docs Rahul confirmed the selection after the technical round.");
    await cands().getByRole("button", { name: "Save status" }).click();
    await settle(a, 2500);
    await say(a, "HIRE-010 selected");
  });
  await step("offer form", async () => {
    await open();
    await cands().getByRole("button", { name: "Offer of Docs Candidate Kiran" }).click();
    await settle(a, 2000);
    console.log("VERIFY HIRE-010 offer panel:", await text(cands()));
    console.log("VERIFY HIRE-010 offer controls:", await ctrls(cands()));
    const add = cands().getByRole("button", { name: /(Record|Add|Create|Make).*offer/i }).first();
    if (await add.count()) { await add.click(); await settle(a, 1500); }
    const f = cands();
    console.log("VERIFY HIRE-010 offer fields:", JSON.stringify(await fields(f)));
    const fill = async (re: RegExp, v: string) => { const x = f.getByLabel(re).first(); if (await x.count()) await x.fill(v); };
    const pick = async (re: RegExp, want: RegExp) => { const x = f.getByLabel(re).first(); if (await x.count()) { const o = await x.locator("option").allInnerTexts(); const hit = o.find((t) => want.test(t)); if (hit) await x.selectOption({ label: hit }); } };
    await fill(/(Offered )?(CTC|salary|package)/i, "850000");
    await fill(/^Position/i, "Python Developer");
    await fill(/Joining date|Date of joining|Start date/i, plusDays(30));
    await fill(/Offer date|Offered on/i, plusDays(0));
    await fill(/(Valid|Expiry|Expires|Accept by|Respond by)/i, plusDays(7));
    await fill(/Location/i, "Hyderabad");
    await pick(/Currency/i, /INR/);
    await pick(/Pay period|per/i, /year/i);
    await pick(/^Status/i, /Offered|Released|Sent/i);
    const ta = f.locator("textarea");
    for (let i = 0; i < await ta.count(); i++) if (!(await ta.nth(i).inputValue())) await ta.nth(i).fill("Hybrid; 3 days a week at the Hyderabad office. Standard Docs Acme benefits.");
    console.log("VERIFY HIRE-010 offer fields filled:", JSON.stringify(await fields(f)));
    await shoot(a, H, "25-offer-form.png", { root, element: f });
    await f.getByRole("button", { name: /^(Save|Record|Create|Add).*(offer)?/i }).filter({ hasNotText: /candidate|status/i }).first().click();
    await settle(a, 3000);
    await say(a, "HIRE-010 offer saved");
    console.log("VERIFY HIRE-010 after:", await text(cands()));
    console.log("VERIFY HIRE-010 after controls:", await ctrls(cands()));
    await shoot(a, H, "26-offer-recorded.png", { root, element: cands() });
  });
  await step("offer letter and status", async () => {
    const letter = path.join(process.env.DOCS_FILES_DIR!, "docs-kiran-offer-letter.pdf");
    const g = await ctx.newPage();
    await g.setContent("<html><body style='font-family:Arial;margin:40px'><h1>Docs Acme Technologies</h1><h2>Offer of employment</h2><p>Dear Docs Candidate Kiran,</p><p>We are pleased to offer you the position of Python Developer in Hyderabad at INR 8,50,000 per year, joining on the date agreed with EduSphere.</p><p>Docs Rahul Hiring Manager</p><p><i>Fictional document for the EduSphere user guide.</i></p></body></html>");
    await g.pdf({ path: letter, format: "A4" });
    await g.close();
    await open();
    await cands().getByRole("button", { name: "Offer of Docs Candidate Kiran" }).click();
    await settle(a, 2000);
    const c = cands();
    await c.locator('input[type="file"]').first().setInputFiles(letter);
    await c.getByRole("button", { name: "Upload", exact: true }).click();
    await settle(a, 3000);
    await say(a, "HIRE-010 letter");
    await c.getByRole("button", { name: "Change status of the offer" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-010 offer status fields:", JSON.stringify(await fields(c)));
    const sel = c.locator("select").filter({ hasText: /Accept|Offer/ }).last();
    const opts = await sel.locator("option").allInnerTexts();
    console.log("VERIFY HIRE-010 offer statuses:", JSON.stringify(opts));
    await sel.selectOption({ label: opts.find((o) => /Accepted/i.test(o))! });
    const note = c.locator("textarea").last();
    if (await note.count()) await note.fill("Kiran accepted by email on 19 Nov 2026.");
    await shoot(a, H, "27-offer-status.png", { root, element: c });
    console.log("VERIFY HIRE-010 status buttons:", await ctrls(c));
    await c.getByRole("button", { name: /^Save/ }).first().click();
    await settle(a, 3000);
    await say(a, "HIRE-010 accepted");
    await open();
    await cands().getByRole("button", { name: "Offer of Docs Candidate Kiran" }).click();
    await settle(a, 2000);
    console.log("VERIFY HIRE-010 final:", await text(cands()));
    await shoot(a, H, "28-offer-accepted.png", { root, element: cands() });
  });
  await step("offers list", async () => {
    await a.locator("nav, aside").getByRole("link", { name: "Offers", exact: true }).first().click();
    await settle(a, 3500);
    console.log("VERIFY HIRE-010 offers page:", a.url(), (await text(a.locator("main"))).slice(0, 1500));
    await shoot(a, H, "29-offers.png", { root });
  });
  await ctx.close();
});
