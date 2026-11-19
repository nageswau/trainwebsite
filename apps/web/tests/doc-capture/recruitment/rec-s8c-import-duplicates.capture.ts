import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S8c (docs/recruitment-crm/documentation-plan.md): DOC-REC-CAN-006 (save extracted), CAN-011 import, CAN-012 duplicates,
// CAN-013 unassigned queue. Runs after rec-s8b. Recruiter A imports 4 rows (one new, a second "Docs Candidate Kiran" with the same
// location and college, Meena's mobile, an error row); the Team Lead merges the probable duplicate into CAN-000002.
const root = REC_ROOT;
const C = "candidates";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, heading: string | RegExp) =>
  p.getByRole("heading", { name: heading, exact: typeof heading === "string" }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const btns = async (l: Locator) => JSON.stringify([...new Set((await l.locator("button, a").allInnerTexts()).map((b) => b.trim()).filter(Boolean))]);
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}

const CSV = [
  "name,mobile,email,source_detail,location,country,state,city,qualification,college,passing_year,experience_months,relevant_experience_months,current_company,notice_days,preferred_role,preferred_locations,tools,languages,linkedin,available_from,willing_to_relocate",
  "Docs Candidate Ravi,9000040003,docs.cand.ravi@example.com,Naukri export Nov 2026,,India,Telangana,Hyderabad,MCA,Docs College of Engineering,2022,36,24,Docs Nimbus Labs,60,Java Developer,Hyderabad;Pune,Git;Jira,English;Telugu,,,Yes",
  "Docs Candidate Kiran,9000040011,docs.kiran.r@example.com,Naukri export Nov 2026,,India,Telangana,Hyderabad,B.Tech,Docs Institute of Technology,2023,30,30,Docs Orbit Softech,30,Python Developer,Hyderabad,Git,English,,,Yes",
  "Docs Candidate Meena,9000040002,docs.cand.meena@example.com,Naukri export Nov 2026,,India,Telangana,Hyderabad,B.Sc,Docs Degree College,2023,18,18,Docs Lumen Analytics,15,Data Analyst,Hyderabad,Excel,English,,,No",
  "Docs Candidate Sana,9000040004,docs.cand.sana@example.com,Naukri export Nov 2026,,India,Telangana,Hyderabad,B.Tech,Docs College of Engineering,2024,twelve,,,,QA Engineer,Hyderabad,,,,,",
].join("\n");

test("Recruitment CRM S8c import and duplicates", async ({ browser }) => {
  test.setTimeout(1_200_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const csv = path.join(process.env.DOCS_FILES_DIR!, "docs-candidates-import.csv");
  writeFileSync(csv, CSV + "\n");

  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  a.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");

  // ===== CAN-006 save extracted details =====
  await step("CAN-006 save extracted", async () => {
    await a.goto(`/recruiter/candidates/${ids.candidates.kiran}`);
    await settle(a, 3500);
    const rs = () => sec(a, "Resume");
    await rs().getByRole("button", { name: "Review extracted details" }).click();
    await settle(a, 2500);
    for (const s of ["PostgreSQL", "Docker"]) {
      await rs().getByLabel(new RegExp(`^${s}`)).first().check();
      await rs().getByLabel(`Level for ${s}`).selectOption({ label: "Intermediate" });
    }
    await shoot(a, C, "31-review-extracted.png", { root, element: rs() });
    await rs().getByRole("button", { name: "Save selected" }).click();
    await settle(a, 3000);
    await say(a, "CAN-006 saved");
    console.log("VERIFY CAN-006 skills after:", await text(sec(a, "Skills")));
    await shoot(a, C, "32-skills-after-resume.png", { root, element: sec(a, "Skills") });
  });

  // ===== CAN-011 import =====
  await step("CAN-011 import", async () => {
    await a.goto("/recruiter/candidates/import");
    await settle(a, 3000);
    await a.getByLabel("Candidate source").selectOption({ label: "Job portals" });
    await a.getByLabel("Basis for holding the details").selectOption({ label: "They shared their details for job placement" });
    await a.getByLabel("Filled-in candidates file").setInputFiles(csv);
    await shoot(a, C, "33-import-form.png", { root });
    await a.getByRole("button", { name: "Check file" }).click();
    await settle(a, 4000);
    await say(a, "CAN-011 checked");
    console.log("VERIFY CAN-011 preview:", (await text(a.locator("main"))).slice(0, 2500));
    console.log("VERIFY CAN-011 preview buttons:", await btns(a.locator("main")));
    await shoot(a, C, "34-import-preview.png", { root, element: sec(a, "Import candidates (CSV or Excel)") });
    await a.locator("main").getByRole("button", { name: /^Import/ }).first().click();
    await settle(a, 5000);
    await say(a, "CAN-011 imported");
    console.log("VERIFY CAN-011 result:", (await text(a.locator("main"))).slice(0, 2500));
    await shoot(a, C, "35-import-result.png", { root, element: sec(a, "Import candidates (CSV or Excel)") });
    await a.goto("/recruiter/candidates/import");
    await settle(a, 3000);
    await shoot(a, C, "36-past-imports.png", { root, element: sec(a, "Past imports") });
    console.log("VERIFY CAN-011 past:", await text(sec(a, "Past imports")));
    await a.goto("/recruiter/candidates");
    await settle(a, 3000);
    console.log("VERIFY CAN-011 list:", (await text(a.locator("main"))).slice(-1500));
  });
  await ctx.close();

  // ===== CAN-012 duplicates (Team Lead) =====
  const lctx = await browser.newContext();
  await noPrefetch(lctx);
  const l = await lctx.newPage();
  l.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  await signIn(l, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  await step("CAN-012 duplicates", async () => {
    await l.goto("/recruiter/candidates/duplicates");
    await settle(l, 3000);
    console.log("VERIFY CAN-012 queue:", await text(l.locator("main")));
    if (/No probable duplicates/.test(await l.locator("main").innerText())) {
      await l.getByRole("button", { name: "Check the whole pool" }).click();
      await settle(l, 4000);
      await say(l, "CAN-012 check pool");
      console.log("VERIFY CAN-012 queue after check:", await text(l.locator("main")));
    }
    await shoot(l, C, "37-duplicate-review.png", { root });
    console.log("VERIFY CAN-012 buttons:", await btns(l.locator("main")));
    const m = l.locator("main");
    await m.getByRole("link", { name: "Review and merge" }).or(m.getByRole("button", { name: "Review and merge" })).first().click();
    await settle(l, 3500);
    console.log("VERIFY CAN-012 compare:", await text(m));
    await shoot(l, C, "38-duplicate-compare.png", { root, fullPage: true });
    await m.getByLabel(/Reason/).fill("Same person: imported again from the Naukri export.");
    await m.getByRole("button", { name: /^Merge CAN-/ }).click();
    await settle(l, 4000);
    await say(l, "CAN-012 merged");
    console.log("VERIFY CAN-012 after merge:", l.url(), (await text(m)).slice(0, 900));
    await shoot(l, C, "39-duplicate-merged.png", { root });
    await l.goto("/recruiter/candidates/duplicates");
    await settle(l, 3000);
    await m.getByRole("button", { name: "Merged", exact: true }).click();
    await settle(l, 2500);
    console.log("VERIFY CAN-012 merged tab:", await text(m));
    await shoot(l, C, "39b-merged-tab.png", { root });
  });

  // ===== CAN-013 unassigned queue (Team Lead) =====
  await step("CAN-013 unassigned", async () => {
    await l.goto("/recruiter/candidates?owner=unassigned");
    await settle(l, 3000);
    console.log("VERIFY CAN-013 unassigned:", (await text(l.locator("main"))).slice(-800));
    await l.goto("/recruiter/candidates");
    await settle(l, 3000);
    await shoot(l, C, "41-candidates-team-lead.png", { root });
  });
  await lctx.close();
});
