import { readFileSync } from "node:fs";
import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S6a (docs/recruitment-crm/documentation-plan.md): DOC-REC-CO-010/011/014 and DASH-001/002. Runs after rec-s5b.
// Beta Systems walks the manual stages (forward, back, lost, reopen, inactive, reopen); Acme gets a company profile document.
const root = REC_ROOT;
const C = "companies";
const D = "dashboard";
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
  if (who === "lead") await signIn(p, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  else await signIn(p, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  return p;
}

test("Recruitment CRM S6a pipeline, documents, board, dashboards", async ({ browser }) => {
  test.setTimeout(900_000);
  const { acme, beta } = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8")).companies;
  const a = await as(browser, "a");
  const pipe = () => sec(a, "Pipeline");
  const openBeta = async () => { await a.goto(`/recruiter/companies/${beta}`); await settle(a, 3000); };
  const move = async (to: string, note?: string) => {
    await pipe().getByLabel("Move to").selectOption({ label: to });
    if (note) await pipe().locator("textarea").first().fill(note);
    await pipe().getByRole("button", { name: "Move", exact: true }).click();
    await settle(a, 2000);
    await say(a, `CO-010 move ${to}`);
  };

  // ===== CO-010 pipeline stage =====
  await openBeta();
  await shoot(a, C, "32-pipeline-card.png", { root, element: pipe() });
  console.log("VERIFY CO-010 move options:", JSON.stringify(await pipe().getByLabel("Move to").locator("option").allInnerTexts()));
  await move("Research Completed", "Read the careers page and LinkedIn.");
  await pipe().getByLabel("Move to").selectOption({ label: "Outreach Sent" });
  await pipe().locator("textarea").first().fill("First email sent to the HR inbox.");
  await shoot(a, C, "33-move-stage-form.png", { root, element: pipe() });
  await pipe().getByRole("button", { name: "Move", exact: true }).click();
  await settle(a, 2000);
  await say(a, "CO-010 move Outreach Sent");
  // moving back needs a reason
  await pipe().getByLabel("Move to").selectOption({ label: "Research Completed" });
  await settle(a, 500);
  console.log("VERIFY CO-010 back label:", await text(pipe()));
  await shoot(a, C, "34-move-back-reason.png", { root, element: pipe() });
  await pipe().locator("textarea").first().fill("The email bounced; checking the address again.");
  await pipe().getByRole("button", { name: "Move", exact: true }).click();
  await settle(a, 2000);
  await say(a, "CO-010 moved back");
  // mark lost, then reopen
  await pipe().getByRole("button", { name: "Mark lost" }).click();
  await settle(a, 1500);
  const lostReasons = await pipe().getByLabel("Reason", { exact: true }).locator("option").allInnerTexts();
  console.log("VERIFY CO-010 lost reasons:", JSON.stringify(lostReasons));
  await pipe().getByLabel("Reason", { exact: true }).selectOption({ index: 1 });
  await pipe().getByLabel("Note (optional)").fill("Hiring frozen until April.");
  await shoot(a, C, "35-mark-lost-form.png", { root, element: pipe() });
  await pipe().getByRole("button", { name: "Yes, mark lost" }).click();
  await settle(a, 2000);
  await say(a, "CO-010 lost");
  await shoot(a, C, "36-marked-lost.png", { root, element: pipe() });
  // only the Team Lead can reopen
  console.log("VERIFY CO-010 recruiter buttons after lost:", JSON.stringify(await pipe().getByRole("button").allInnerTexts()));
  const lead = await as(browser, "lead");
  const lpipe = () => sec(lead, "Pipeline");
  const leadReopen = async (why: string, shot?: string) => {
    await lead.goto(`/recruiter/companies/${beta}`);
    await settle(lead, 3000);
    await lpipe().getByRole("button", { name: "Reopen" }).click();
    await settle(lead, 800);
    await lpipe().getByLabel("Reason", { exact: true }).fill(why);
    if (shot) await shoot(lead, C, shot, { root, element: lpipe() });
    await lpipe().getByRole("button", { name: "Yes, reopen" }).click();
    await settle(lead, 2000);
    await say(lead, "CO-010 reopened");
    console.log("VERIFY CO-010 after reopen:", await text(lpipe()));
  };
  await leadReopen("They called back: two openings in January.", "37-reopen-form.png");
  // mark inactive (recruiter), then the Team Lead reopens
  await openBeta();
  await pipe().getByRole("button", { name: "Mark inactive" }).click();
  await settle(a, 1500);
  console.log("VERIFY CO-010 inactive reasons:", JSON.stringify(await pipe().getByLabel("Reason", { exact: true }).locator("option").allInnerTexts()));
  await pipe().getByLabel("Reason", { exact: true }).selectOption({ index: 1 });
  await pipe().getByRole("button", { name: "Yes, mark inactive" }).click();
  await settle(a, 2000);
  await say(a, "CO-010 inactive");
  await shoot(a, C, "38-marked-inactive.png", { root, element: pipe() });
  await leadReopen("Back in touch after the restructuring.");
  await lead.context().close();
  await openBeta();
  await shoot(a, C, "39-stage-history.png", { root, element: sec(a, "Stage history") });
  console.log("VERIFY CO-010 history:", await text(sec(a, "Stage history")));

  // ===== CO-011 documents, timeline, shared profiles (Acme) =====
  await a.goto(`/recruiter/companies/${acme}`);
  await settle(a, 3000);
  console.log("VERIFY CO-010 acme pipeline:", await text(pipe()));
  const docs = sec(a, "Documents");
  console.log("VERIFY CO-011 doc kinds:", JSON.stringify(await docs.getByLabel("Document type").locator("option").allInnerTexts()));
  await docs.getByLabel("Document type").selectOption({ label: "Company profile" });
  await docs.getByLabel("Linked meeting (optional)").selectOption({ index: 1 });
  await docs.getByLabel("File (PDF, JPEG or PNG, up to 20 MB)").setInputFiles(path.join(process.env.DOCS_FILES_DIR!, "docs-acme-profile.pdf"));
  await shoot(a, C, "40-upload-document.png", { root, element: docs });
  await docs.getByRole("button", { name: "Upload document" }).click();
  await settle(a, 2500);
  await say(a, "CO-011 upload");
  await shoot(a, C, "41-documents.png", { root, element: sec(a, "Documents") });
  await a.reload();
  await settle(a, 3500);
  await shoot(a, C, "42-timeline.png", { root, element: sec(a, "Timeline") });
  console.log("VERIFY CO-011 timeline:", await text(sec(a, "Timeline")));
  const shares = a.getByRole("heading", { name: /^Shared profiles/ }).first().locator("xpath=ancestor::section[1]");
  console.log("VERIFY CO-011 shares:", await text(shares));

  // ===== CO-014 pipeline board =====
  await a.goto("/recruiter/pipeline");
  await settle(a, 3000);
  await shoot(a, C, "43-pipeline-board.png", { root, fullPage: true });
  await a.getByRole("link", { name: /^Meeting Booked/ }).first().click();
  await settle(a, 2500);
  console.log("VERIFY CO-014 filtered:", a.url(), await text(a.locator("main")));
  await shoot(a, C, "44-pipeline-board-stage.png", { root });

  // ===== DASH-001 recruiter dashboard =====
  await a.goto("/recruiter/dashboard");
  await settle(a, 3000);
  await shoot(a, D, "05-recruiter-dashboard.png", { root });
  await shoot(a, D, "06-recruiter-dashboard-full.png", { root, fullPage: true });
  await a.getByRole("link", { name: /Follow-ups Due/ }).first().click();
  await settle(a, 2500);
  console.log("VERIFY DASH-001 tile link:", a.url());
  await a.context().close();

  // ===== DASH-002 Team Lead dashboard =====
  const l = await as(browser, "lead");
  await l.goto("/recruiter/dashboard");
  await settle(l, 3000);
  await shoot(l, D, "07-team-lead-dashboard.png", { root });
  await l.getByLabel("Recruiter", { exact: true }).selectOption({ label: "Docs Recruiter A" });
  await l.getByRole("button", { name: "Show", exact: true }).click();
  await settle(l, 3000);
  console.log("VERIFY DASH-002 one recruiter:", l.url(), (await text(l.locator("main"))).slice(0, 600));
  await shoot(l, D, "08-team-lead-dashboard-one-recruiter.png", { root });
  await l.goto("/recruiter/pipeline");
  await settle(l, 3000);
  console.log("VERIFY CO-014 lead board:", (await text(l.locator("main"))).slice(0, 900));
  await l.context().close();
});
