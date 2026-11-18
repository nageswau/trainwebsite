import { readFileSync } from "node:fs";
import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S6b (docs/recruitment-crm/documentation-plan.md): DOC-REC-CO-012/013/015. Runs after rec-s6a.
// The Team Lead imports docs-companies-import.csv (Docs Gamma Labs, a duplicate "Docs Gamma Labs Pvt Ltd", a matched Acme row and an error row),
// merges the duplicate company and contact, and adds a cadence that Recruiter A starts on an Acme message.
const root = REC_ROOT;
const C = "companies";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function as(browser: Browser, who: "a" | "lead") {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  p.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  if (who === "lead") await signIn(p, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  else await signIn(p, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  return p;
}

test("Recruitment CRM S6b import, merge, cadences", async ({ browser }) => {
  test.setTimeout(900_000);
  JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8")); // rec-ids.json must exist (S2)
  const l = await as(browser, "lead");

  // ===== CO-012 import =====
  await l.goto("/recruiter/companies/import");
  await settle(l, 3000);
  await shoot(l, C, "45-import-page.png", { root });
  await l.getByLabel("Filled-in companies file").setInputFiles(path.join(process.env.DOCS_FILES_DIR!, "docs-companies-import.csv"));
  await l.getByRole("button", { name: "Check file" }).click();
  await settle(l, 4000);
  console.log("VERIFY CO-012 preview:", await text(l.locator("main")));
  await shoot(l, C, "46-import-check.png", { root, element: l.getByRole("heading", { name: "3. Check the rows" }).locator("xpath=..") });
  await l.getByRole("button", { name: /^Import \d+ new row/ }).click();
  await settle(l, 5000);
  await say(l, "CO-012 import");
  console.log("VERIFY CO-012 report:", await text(l.locator("main")));
  await shoot(l, C, "47-import-result.png", { root, element: l.getByRole("heading", { name: "Import result" }).locator("xpath=..") });
  await l.reload();
  await settle(l, 3000);
  await shoot(l, C, "48-past-imports.png", { root, element: sec(l, "Past imports") });

  // ===== CO-013 merge a duplicate company =====
  await l.goto("/recruiter/companies");
  await settle(l, 3000);
  const rowCode = async (name: string) => {
    const row = l.getByRole("row").filter({ has: l.getByRole("link", { name, exact: true }) }).first();
    return ((await row.innerText()).match(/CMP-\d+/) ?? [""])[0];
  };
  const gammaCode = await rowCode("Docs Gamma Labs");
  const dupCode = await rowCode("Docs Gamma Labs Pvt Ltd");
  console.log("VERIFY CO-013 codes:", gammaCode, dupCode);
  await l.getByRole("link", { name: "Docs Gamma Labs", exact: true }).first().click();
  await settle(l, 3500);
  const gammaUrl = l.url();
  await shoot(l, C, "49-imported-company.png", { root });
  await l.getByRole("link", { name: "Merge a duplicate", exact: true }).first().click();
  await settle(l, 2500);
  await l.getByLabel("Duplicate company's code").fill(dupCode);
  await l.getByRole("button", { name: "Compare" }).click();
  await settle(l, 3000);
  // keep the duplicate's website and priority to show the per-field choice
  const pick = l.getByRole("radio", { name: /^Keep https:\/\/gammalabs/ });
  if (await pick.count()) await pick.first().check();
  await l.getByLabel("Reason (optional)").fill("Same company entered twice in the import.");
  console.log("VERIFY CO-013 compare:", await text(l.locator("main")));
  await shoot(l, C, "50-merge-company-compare.png", { root, fullPage: true });
  await l.getByRole("button", { name: `Merge ${dupCode}` }).click();
  await settle(l, 3500);
  await say(l, "CO-013 company merged");
  await shoot(l, C, "51-merge-company-done.png", { root });

  // ===== CO-013 merge a duplicate contact =====
  await l.goto(gammaUrl);
  await settle(l, 3500);
  console.log("VERIFY CO-013 contacts:", await text(sec(l, "Contacts")));
  await l.getByRole("link", { name: /Merge a duplicate into Docs Kiran Talent Lead/ }).first().click();
  await settle(l, 2500);
  const dupContact = l.getByLabel("Duplicate contact");
  console.log("VERIFY CO-013 contact options:", JSON.stringify(await dupContact.locator("option").allInnerTexts()));
  await dupContact.selectOption({ label: (await dupContact.locator("option").allInnerTexts()).find((o) => o.startsWith("Docs Kiran R"))! });
  await settle(l, 2500);
  await l.getByLabel("Reason (optional)").fill("Same person, second email address.");
  console.log("VERIFY CO-013 contact compare:", await text(l.locator("main")));
  await shoot(l, C, "52-merge-contact-compare.png", { root, fullPage: true });
  await l.getByRole("button", { name: "Merge contact" }).click();
  await settle(l, 3500);
  await say(l, "CO-013 contact merged");
  await shoot(l, C, "53-merge-contact-done.png", { root, element: sec(l, "Contacts") });

  // imported companies are unassigned: the Team Lead assigns Gamma to Recruiter A
  await l.goto(gammaUrl);
  await settle(l, 3500);
  const asg = sec(l, "Assignment");
  const box = asg.getByRole("combobox", { name: /Assign to/ });
  await box.click();
  await box.fill("Docs Recruiter A");
  await settle(l, 1200);
  await l.getByRole("option", { name: /Docs Recruiter A/ }).first().click();
  await asg.getByRole("button", { name: "Assign", exact: true }).click();
  await settle(l, 800);
  await shoot(l, C, "58-assign-imported-company.png", { root, element: asg });
  await l.getByRole("button", { name: "Yes, assign" }).click();
  await settle(l, 2500);
  await say(l, "CO-012 assigned");

  // ===== CO-015 cadences (Team Lead) =====
  await l.goto("/recruiter/manager/cadences");
  await settle(l, 3000);
  await l.getByRole("button", { name: "Add cadence" }).first().click();
  await settle(l, 1000);
  const f = l.getByRole("form", { name: "Add a cadence" });
  await f.getByLabel("Name (required)").fill("Docs No-reply follow-up");
  await f.getByLabel("Description (optional)").fill("For a first email that gets no answer.");
  const stepCount = await f.getByRole("group", { name: /^Step \d+$/ }).count();
  console.log("VERIFY CO-015 default steps:", stepCount);
  if (stepCount < 3) await f.getByRole("button", { name: "Add step" }).click();
  const setStep = async (i: number, day: string, channel: string) => {
    await f.getByLabel(`Step ${i} day`).fill(day);
    await f.getByLabel(`Step ${i} channel`).selectOption({ label: channel });
  };
  await setStep(1, "0", "Email");
  await setStep(2, "3", "LinkedIn");
  await setStep(3, "7", "Call");
  await shoot(l, C, "54-add-cadence-form.png", { root, element: f });
  await f.getByRole("button", { name: "Add cadence" }).click();
  await settle(l, 2500);
  await say(l, "CO-015 cadence added");
  await shoot(l, C, "55-cadences.png", { root });
  await l.context().close();

  // ===== CO-015 start a cadence on a message (Recruiter A) =====
  const a = await as(browser, "a");
  // Acme's contacts have replied or have a meeting, so the cadence starts on a first email to Gamma's Kiran (To is set before the composer opens)
  await a.goto(gammaUrl);
  await settle(a, 3500);
  const msgs = () => sec(a, "Messages");
  await msgs().getByLabel("To").selectOption({ label: "Docs Kiran Talent Lead" });
  await msgs().getByRole("button", { name: "Send email" }).click();
  await settle(a, 1000);
  await msgs().getByLabel("Template").selectOption({ label: "Company introduction" });
  await settle(a, 1500);
  await msgs().getByRole("button", { name: "Send email" }).last().click();
  await settle(a, 3000);
  await say(a, "CO-015 email to Kiran");
  await a.reload();
  await settle(a, 3500);
  const start = a.getByRole("button", { name: /^Start cadence for Docs Kiran/ });
  console.log("VERIFY CO-015 start buttons:", await start.count());
  await start.first().click();
  await settle(a, 800);
  const sf = a.getByRole("form", { name: "Start an outreach cadence" });
  await sf.getByLabel("Cadence").selectOption({ label: "Docs No-reply follow-up" });
  await settle(a, 500);
  await shoot(a, C, "56-start-cadence.png", { root, element: sf.locator("xpath=ancestor::li[1]") });
  await sf.getByRole("button", { name: "Start", exact: true }).click();
  await settle(a, 2500);
  await say(a, "CO-015 cadence started");
  const run = a.getByText(/^Cadence: Docs No-reply follow-up/).first();
  console.log("VERIFY CO-015 run:", await run.innerText().catch(() => "not found"));
  await shoot(a, C, "57-cadence-running.png", { root, element: run.locator("xpath=ancestor::li[1]") });
  await a.context().close();
});
