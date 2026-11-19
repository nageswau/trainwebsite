import { test, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S12b (docs/recruitment-crm/documentation-plan.md): DOC-REC-HIRE-014..016 views. Runs after rec-s12a.
// Owner decisions 2026-11-19: the invoice draft is kept (Discard draft opened and cancelled; Issue invoice never clicked; R3) and the
// dropout is documented form-only (Record dropout opened and cancelled) so Kiran stays a successful placement. Nothing is saved here.
const root = REC_ROOT;
const H = "hiring";
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const box = (p: Page, label: RegExp) =>
  p.locator("main").getByText(label).first().locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
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

test("Recruitment CRM S12b placement views", async ({ browser }) => {
  test.setTimeout(900_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  // Every confirm() is dismissed: nothing on this page is saved.
  a.on("dialog", (d) => { console.log(`VERIFY dialog (dismissed): ${d.message()}`); void d.dismiss(); });
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  await a.goto("/recruiter/placements");
  await settle(a, 3000);
  await a.locator("main").getByRole("button", { name: /^Invoice drafts/ }).or(a.locator("main").getByRole("link", { name: /^Invoice drafts/ })).first().click();
  await settle(a, 2500);
  console.log("VERIFY HIRE-014 drafts tab:", (await text(a.locator("main"))).slice(0, 900));
  await shoot(a, H, "38-placements-invoice-drafts.png", { root });
  await a.locator("main").getByRole("link", { name: "Docs Candidate Kiran" }).first().click();
  await settle(a, 3500);
  const url = a.url();
  const open = async () => { await a.goto(url); await settle(a, 3500); };

  // ===== HIRE-014 invoice draft (view; Discard opened and cancelled) =====
  await step("HIRE-014", async () => {
    const inv = box(a, /^Draft to review$/);
    console.log("VERIFY HIRE-014 card:", await text(inv));
    await shoot(a, H, "39-invoice-draft.png", { root, element: inv });
    await inv.getByRole("button", { name: "Discard draft" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-014 discard ui:", await text(inv));
    console.log("VERIFY HIRE-014 discard fields:", JSON.stringify(await fields(inv)), await ctrls(inv));
    await shoot(a, H, "40-discard-draft-form.png", { root, element: inv });
    const cancel = inv.getByRole("button", { name: /^(Cancel|Keep|No)/ }).first();
    if (await cancel.count()) await cancel.click();
    await open();
    console.log("VERIFY HIRE-014 still draft:", await text(box(a, /^Draft to review$/)));
  });

  // ===== HIRE-015 guarantee and dropout form (opened and cancelled) =====
  await step("HIRE-015", async () => {
    const g = box(a, /^In guarantee$/);
    console.log("VERIFY HIRE-015 card:", await text(g));
    await shoot(a, H, "41-guarantee.png", { root, element: g });
    await g.getByRole("button", { name: "Record dropout" }).click();
    await settle(a, 1500);
    console.log("VERIFY HIRE-015 dropout ui:", await text(g));
    console.log("VERIFY HIRE-015 dropout fields:", JSON.stringify(await fields(g)), await ctrls(g));
    await shoot(a, H, "42-record-dropout-form.png", { root, element: g });
    const cancel = g.getByRole("button", { name: /^(Cancel|Keep|No)/ }).first();
    if (await cancel.count()) await cancel.click();
    await open();
    console.log("VERIFY HIRE-015 still:", await text(box(a, /^In guarantee$/)));
  });

  // ===== HIRE-016 satisfaction card =====
  await step("HIRE-016", async () => {
    const s = a.getByRole("heading", { name: "Satisfaction" }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");
    console.log("VERIFY HIRE-016 card:", await text(s));
    await shoot(a, H, "43-satisfaction.png", { root, element: s });
  });
  await ctx.close();
});
