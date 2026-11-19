import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import { mailCount, mailLink, noPrefetch, REC_ROOT, shoot } from "../shoot";

// Recruitment CRM S8e (docs/recruitment-crm/documentation-plan.md): DOC-REC-CAND-001..004 and CAN-014. Runs after rec-s8d.
// Docs Candidate Nisha (an external person, @example.com because candidate emails refuse .test) applies on the public careers page
// for Docs Python Developer, tracks the application, creates a candidate account, verifies it from Mailpit and edits her profile.
// Recruiter A then sees her on New website registrations.
const root = REC_ROOT;
const P = "candidate-portal";
const EMAIL = "docs.cand.nisha@example.com";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const fields = (l: Locator) => l.evaluate((el) => [...el.querySelectorAll("input, select, textarea")].map((e) => {
  const f = e as HTMLInputElement;
  const lab = f.id ? document.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.textContent?.trim() : f.closest("label")?.textContent?.trim();
  return `${f.type} "${(lab || f.getAttribute("aria-label") || f.name || "").slice(0, 80)}"`;
}));
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}
const pw = () => process.env.DOCS_TEST_PASSWORD!;
const form0 = (p: Page) => p.locator("main form").filter({ has: p.getByRole("button", { name: "Submit application" }) }).first();
const body = async (p: Page) => ((await p.locator("main").count()) ? p.locator("main").first() : p.locator("body"));

test("Recruitment CRM S8e candidate portal", async ({ browser }) => {
  test.setTimeout(1_200_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const resume = path.join(process.env.DOCS_FILES_DIR!, "docs-nisha-resume.pdf");
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  await p.setContent("<html><body style='font-family:Arial;margin:40px'><h1>Docs Candidate Nisha</h1><p>docs.cand.nisha@example.com · +91 90000 40021</p><h2>Skills</h2><p>Python, Django, FastAPI, SQL</p><h2>Experience</h2><p>Junior Developer, Docs Brightpath Tech, 2024 to present</p><h2>Education</h2><p>B.Tech, Docs College of Engineering, 2024</p></body></html>");
  await p.pdf({ path: resume, format: "A4" });
  let code = "";

  // ===== CAND-001 careers page and apply =====
  await step("CAND-001 apply", async () => {
    await p.goto("/it/careers");
    await settle(p, 3500);
    await shoot(p, P, "01-careers.png", { root, fullPage: true });
    const card = p.locator("article, li, .card").filter({ hasText: "Docs Python Developer" }).first();
    await card.getByRole("link", { name: /Apply online/ }).or(card.getByRole("button", { name: /Apply online/ })).first().click();
    await settle(p, 3500);
    console.log("VERIFY CAND-001 apply url:", p.url());
    console.log("VERIFY CAND-001 apply fields:", JSON.stringify(await fields(p.locator("main"))));
    console.log("VERIFY CAND-001 apply text:", (await text(p.locator("main"))).slice(0, 1500));
    const fill = async (re: RegExp, v: string) => { const f = p.locator("main").getByLabel(re).first(); if (await f.count()) await f.fill(v); };
    await fill(/^(Full name|Name)/i, "Docs Candidate Nisha");
    await fill(/^Email/i, EMAIL);
    await fill(/(Mobile|Phone)/i, "9000040021");
    await fill(/(Cover|Message|Why)/i, "I build Python APIs with FastAPI and would like to join Docs Acme.");
    const file = p.locator("main input[type=file]").first();
    if (await file.count()) await file.setInputFiles(resume);
    await form0(p).getByRole("checkbox").first().check();
    const form = p.locator("main form").filter({ has: p.getByRole("button", { name: "Submit application" }) }).first();
    await shoot(p, P, "02-apply-form.png", { root, element: form });
    await p.locator("main").getByRole("button", { name: "Submit application" }).click();
    await settle(p, 4000);
    await say(p, "CAND-001 applied");
    const t = await text(await body(p));
    console.log("VERIFY CAND-001 after:", t.slice(0, 2500));
    code = t.match(/\b([A-Z]{2,5}-[A-Z0-9-]{4,})\b/)?.[1] ?? "";
    console.log("VERIFY CAND-001 tracking code:", code);
    await shoot(p, P, "03-application-sent.png", { root });
  });

  // ===== CAND-002 track =====
  await step("CAND-002 track", async () => {
    await p.goto("/it/careers");
    await settle(p, 3000);
    await p.locator('input[name="code"]').fill(code);
    await p.locator('input[name="email"]').fill(EMAIL);
    await p.getByRole("button", { name: "Track application" }).click();
    await settle(p, 3500);
    await say(p, "CAND-002 tracked");
    console.log("VERIFY CAND-002 result:", p.url(), (await text(await body(p))).slice(0, 2000));
    await shoot(p, P, "04-track-application.png", { root });
  });

  // ===== CAND-003 register and verify =====
  await step("CAND-003 register", async () => {
    await p.goto("/it/careers/register");
    await settle(p, 3000);
    await p.getByLabel("Full name").fill("Docs Candidate Nisha");
    await p.getByLabel("Email").fill(EMAIL);
    await p.getByLabel("Mobile (optional)").fill("9000040021");
    await p.getByLabel("Password", { exact: true }).fill(pw());
    await p.getByLabel("Confirm password").fill(pw());
    await p.getByRole("checkbox").first().check();
    await shoot(p, P, "05-register.png", { root });
    const before = await mailCount(EMAIL);
    await p.getByRole("button", { name: "Create candidate account" }).click();
    await settle(p, 3500);
    await say(p, "CAND-003 registered");
    console.log("VERIFY CAND-003 after:", (await text(await body(p))).slice(0, 800));
    await shoot(p, P, "06-check-email.png", { root });
    const link = await mailLink(EMAIL, before, /https?:\/\/\S+verify\S*token=[\w.-]+/);
    console.log("VERIFY CAND-003 link path:", link.split("?")[0]);
    await p.goto(link);
    await settle(p, 3000);
    await shoot(p, P, "07-verify-email.png", { root });
    await p.getByRole("button", { name: "Verify my email" }).click();
    await settle(p, 3500);
    await say(p, "CAND-003 verified");
    console.log("VERIFY CAND-003 verified page:", p.url(), (await text(await body(p))).slice(0, 800));
    await shoot(p, P, "07b-email-verified.png", { root });
  });

  // ===== CAND-004 sign in and profile =====
  await step("CAND-004 profile", async () => {
    await p.goto("/it/login");
    await settle(p, 2000);
    await p.fill("#login-email", EMAIL);
    await p.fill("#login-password", pw());
    await p.click("button:has-text('Sign in securely')");
    await settle(p, 5000);
    console.log("VERIFY CAND-004 landing:", p.url());
    console.log("VERIFY CAND-004 nav:", JSON.stringify((await p.locator("nav a, aside a").allInnerTexts()).map((s) => s.trim()).filter(Boolean)));
    const b = await body(p);
    console.log("VERIFY CAND-004 page:", (await text(b)).slice(0, 2500));
    console.log("VERIFY CAND-004 fields:", JSON.stringify(await fields(b)));
    console.log("VERIFY CAND-004 buttons:", JSON.stringify([...new Set((await b.locator("button").allInnerTexts()).map((x) => x.trim()))]));
    await shoot(p, P, "08-portal-profile.png", { root, fullPage: true });
    const fill = async (re: RegExp, v: string) => { const f = b.getByLabel(re).first(); if (await f.count() && await f.isEditable()) await f.fill(v); };
    await fill(/^City/i, "Hyderabad");
    await fill(/Preferred roles/i, "Python Developer");
    await fill(/Total experience/i, "14");
    const save = b.getByRole("button", { name: /^Save/ }).first();
    if (await save.count()) { await save.click(); await settle(p, 3000); await say(p, "CAND-004 saved"); }
    await shoot(p, P, "09-profile-saved.png", { root });
  });
  await step("CAND-004 change email", async () => {
    const m = await body(p);
    const open = m.getByRole("button", { name: /Change email/i });
    if (await open.count()) { await open.first().click(); await settle(p, 1500); }
    console.log("VERIFY CAND-004 email fields:", JSON.stringify(await fields(m)));
    await m.getByLabel(/New email/i).fill("docs.cand.nisha.new@example.com");
    await m.getByLabel(/Current password/i).fill(pw());
    await shoot(p, P, "10-change-email.png", { root, element: m.locator("form").filter({ has: p.getByLabel(/New email/i) }).first() });
    await m.getByRole("button", { name: /(Send|Change|Update).*(email|link)?/i }).filter({ hasNotText: /password/i }).last().click();
    await settle(p, 3000);
    await say(p, "CAND-004 email change");
    console.log("VERIFY CAND-004 email after:", (await text(m)).slice(0, 600));
  });
  ids.portal = { nisha: EMAIL, trackingCode: code };
  writeFileSync(process.env.DOCS_REC_FILE!, JSON.stringify(ids, null, 2));
  await ctx.close();

  // ===== CAN-014 website registrations (Recruiter A) =====
  const actx = await browser.newContext();
  await noPrefetch(actx);
  const a = await actx.newPage();
  await a.goto("/it/login");
  await a.fill("#login-email", "docs.rec.a@example.test");
  await a.fill("#login-password", pw());
  await a.click("button:has-text('Sign in securely')");
  await a.waitForURL(/\/recruiter\/dashboard/);
  await step("CAN-014", async () => {
    await a.goto("/recruiter/website-registrations");
    await settle(a, 3500);
    console.log("VERIFY CAN-014 list:", (await text(a.locator("main"))).slice(0, 2000));
    console.log("VERIFY CAN-014 buttons:", JSON.stringify([...new Set((await a.locator("main button, main a").allInnerTexts()).map((b) => b.trim()).filter(Boolean))]));
    await shoot(a, "candidates", "44-website-registrations.png", { root });
  });
  await actx.close();
});
