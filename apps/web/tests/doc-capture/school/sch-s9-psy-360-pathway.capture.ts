import { readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S9 (docs/school-crm/documentation-plan.md): DOC-SCH-PSY-001..004, DOC-SCH-S360-001, DOC-SCH-SADM-006,
// DOC-SCH-RPT-006. Runs after sch-s8.
const PSY = "psychometric-team";
const S360 = "student-360";
const ADM = "admin-schools";
const RPT = "reports";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").first().innerText()).replace(/\s+/g, " ");
const card = (p: Page, heading: string | RegExp) => p.locator(".card, .action-card, section").filter({ has: p.getByRole("heading", { name: heading }) }).last();
const ist = (days: number) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);

async function fresh(browser: Browser, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}
async function pick(p: Page, inputId: string, text: string) {
  await p.fill(`#${inputId}`, text);
  await p.getByRole("listbox").getByRole("option", { name: new RegExp(text) }).first().click();
}

test("School CRM S9 psychometric, 360 and overseas pathway", async ({ browser }) => {
  test.setTimeout(900_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));

  // ===== PSY-001..004 =====
  const pt = await fresh(browser);
  const p = pt.page;
  await signIn(p, "school.psychometric@edusphere.local", "seed", /\/school\/psychometric-team\//);
  await shoot(p, PSY, "01-dashboard.png", opts);
  await pick(p, "psych-student", "Docs Student Ananya");
  await p.fill("#psych-type", "Aptitude Test");
  await shoot(p, PSY, "02-assign-assessment-form.png", { ...opts, center: p.locator("#psych-type") });
  await p.getByRole("button", { name: "Assign assessment" }).click();
  await expect(p.getByText("Assessment assigned.")).toBeVisible();
  await shoot(p, PSY, "03-assessment-assigned.png", { ...opts, center: p.getByText("Assessment assigned.") });
  const row = () => card(p, "Assessments").getByRole("row", { name: /Docs Student Ananya.*Aptitude Test/ });
  await row().getByRole("button", { name: "Attach report" }).click();
  await p.fill("#report-url", "https://reports.example.test/aptitude/ananya.pdf");
  await shoot(p, PSY, "04-attach-report.png", { ...opts, center: p.locator("#report-url") });
  await card(p, "Attach report").getByRole("button", { name: "Attach" }).click();
  await expect(p.getByText("Report attached.")).toBeVisible();
  await say(p, "report attached");
  await row().getByRole("button", { name: /Record results/ }).click();
  await p.fill("#psy-result-test-date", ist(-2));
  await p.fill("#psy-result-strengths", "Spatial reasoning, Creativity");
  await p.fill("#psy-result-interest-areas", "Design, Engineering");
  await p.fill("#psy-result-personality-indicators", "Curious, " + "X".repeat(85));
  await p.getByRole("button", { name: "Save results" }).click();
  await p.waitForTimeout(800);
  await say(p, "results invalid item");
  await shoot(p, PSY, "05-results-validation.png", { ...opts, center: p.locator("#psy-result-personality-indicators") });
  await p.fill("#psy-result-personality-indicators", "Curious, Persistent");
  await p.fill("#psy-result-recommended-careers", "Industrial designer, Mechanical engineer");
  await p.fill("#psy-result-recommended-stream", "PCM with design");
  await p.fill("#psy-result-counsellor-remarks", "Strong fit for design-led engineering programmes.");
  await p.fill("#psy-result-parent-discussion-on", ist(-1));
  await p.fill("#psy-result-follow-up-on", ist(30));
  await shoot(p, PSY, "06-results-form.png", { ...opts, element: card(p, /^Results — /) });
  await p.getByRole("button", { name: "Save results" }).click();
  await expect(p.getByText("Results saved.")).toBeVisible();
  await shoot(p, PSY, "07-results-saved.png", { ...opts, center: p.getByText("Results saved.") });
  console.log(`VERIFY assessments: ${(await card(p, "Assessments").innerText()).replace(/\s+/g, " ").slice(0, 500)}`);
  // PSY-004 bulk
  const tpl = (await (await p.request.get("/api/v1/school/psychometric-team/records/bulk-template")).text()).replace(/^﻿/, "").split(/\r?\n/).filter(Boolean);
  const h = tpl[0].split(",");
  console.log(`VERIFY assessments template header: ${tpl[0]}`);
  const fill = (name: string, v: Record<string, string>) => { const r = tpl.find((l) => l.includes(name))!.split(","); h.forEach((c, i) => { if (v[c] !== undefined) r[i] = v[c]; }); return r.join(","); };
  const csv = [tpl[0], fill("Docs Student Sara", { assessment_type: "Interest Inventory" }), fill("Docs Student Nisha", { assessment_type: "Aptitude Test", report_url: "not-a-url" })].join("\n");
  const csvPath = path.join(os.tmpdir(), "docs-assessments.csv");
  writeFileSync(csvPath, csv);
  const bulk = p.locator("details").filter({ hasText: "Bulk entry — assessments (CSV)" });
  await bulk.locator("summary").first().click();
  await bulk.locator('input[type="file"]').setInputFiles(csvPath);
  await bulk.getByRole("button", { name: /Upload/ }).click();
  await expect(bulk.getByRole("heading", { name: "Upload result" })).toBeVisible({ timeout: 60_000 });
  console.log(`VERIFY bulk assessments: ${(await bulk.innerText()).replace(/\s+/g, " ").slice(-400)}`);
  await shoot(p, PSY, "08-bulk-assessments-report.png", { ...opts, center: bulk.getByRole("heading", { name: "Upload result" }) });
  const students = await (await p.request.get("/api/v1/school/portfolio-students")).json();
  const ananya = students.find((s: { full_name: string }) => s.full_name === "Docs Student Ananya").id;
  await p.goto(`/school/psychometric-team/students/${ananya}/360?tab=psychometric_assessment`);
  await shoot(p, S360, "05-psychometric-tab-psychometric-team.png", opts);
  await pt.ctx.close();

  // ===== S360-001 school role (Coordinator) =====
  {
    const f = await fresh(browser);
    const q = f.page;
    await signIn(q, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
    await q.goto(`/school/coordinator/students/${ananya}/360`);
    await expect(q.getByRole("tablist", { name: "Student record sections" })).toBeVisible();
    console.log(`VERIFY CO tabs: ${JSON.stringify(await q.getByRole("tab").allInnerTexts())}`);
    await shoot(q, S360, "01-overview-school-role.png", opts);
    const arjun = students.find((s: { full_name: string }) => s.full_name === "Docs Student Arjun").id;
    await q.goto(`/school/coordinator/students/${arjun}/360?tab=examination_results`);
    console.log(`VERIFY exam tab (Arjun): ${(await q.locator("#s360-panel").innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
    await shoot(q, S360, "02-examination-results.png", opts);
    await q.goto(`/school/coordinator/students/${ananya}/360`);
    await q.getByRole("tab", { name: /Edusphere Programs/ }).click();
    console.log(`VERIFY programs tab: ${(await q.locator("#s360-panel").innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
    await shoot(q, S360, "03-edusphere-programs.png", opts);
    await q.goto(`/school/coordinator/students/${ananya}/360?tab=career_guidance`);
    console.log(`VERIFY deep link panel: ${(await q.locator("#s360-panel").innerText()).replace(/\s+/g, " ").slice(0, 200)}`);
    await f.ctx.close();
  }
  // Service role view (Academic Team) with Restricted tabs.
  {
    const f = await fresh(browser);
    const q = f.page;
    await signIn(q, "school.academic1@edusphere.local", "seed", /\/school\/academic-team\//);
    await q.goto(`/school/academic-team/students/${ananya}/360`);
    console.log(`VERIFY AT tabs: ${JSON.stringify(await q.getByRole("tab").allInnerTexts())}`);
    await q.getByRole("tab", { name: /Attendance/ }).click();
    await shoot(q, S360, "04-restricted-tab-service-role.png", opts);
    await f.ctx.close();
  }
  // Mobile.
  {
    const f = await fresh(browser, { width: 390, height: 844 });
    await signIn(f.page, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
    await f.page.goto(`/school/coordinator/students/${ananya}/360`);
    await f.page.getByRole("tablist").scrollIntoViewIfNeeded();
    await shoot(f.page, S360, "06-mobile-tabs.png", opts);
    await f.ctx.close();
  }

  // ===== SADM-006 school applications (Overseas Admin) =====
  {
    const f = await fresh(browser);
    const a = f.page;
    await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
    await a.goto("/overseas/admin/school-applications");
    await expect(a.getByRole("heading", { name: "Start an Overseas application for a School student" })).toBeVisible();
    await shoot(a, ADM, "31-school-applications-page.png", opts);
    await pick(a, "bridge-school", "Sunrise Public School");
    await pick(a, "bridge-student", "Docs Student Ananya");
    const uniOpts = await a.locator("#bridge-university option").allInnerTexts();
    console.log(`VERIFY universities: ${JSON.stringify(uniOpts.slice(0, 5))}`);
    await a.selectOption("#bridge-university", { index: 1 });
    await a.fill("#bridge-intake", "Fall 2027");
    await shoot(a, ADM, "32-school-application-form.png", { ...opts, element: card(a, "Start an Overseas application for a School student") });
    await a.getByRole("button", { name: "Start application" }).click();
    const started = a.getByText(/Application started for/);
    await expect(started).toBeVisible();
    await say(a, "application started");
    await shoot(a, ADM, "33-school-application-started.png", { ...opts, center: started });
    // Duplicate.
    await pick(a, "bridge-school", "Sunrise Public School");
    await pick(a, "bridge-student", "Docs Student Ananya");
    await a.selectOption("#bridge-university", { index: 1 });
    await a.fill("#bridge-intake", "Fall 2027");
    await a.getByRole("button", { name: "Start application" }).click();
    await a.waitForTimeout(1200);
    await say(a, "duplicate application");
    // Second student, second university.
    await pick(a, "bridge-school", "Sunrise Public School");
    await pick(a, "bridge-student", "Docs Student Arjun");
    await a.selectOption("#bridge-university", { index: 2 });
    await a.fill("#bridge-intake", "Fall 2027");
    await a.getByRole("button", { name: "Start application" }).click();
    await expect(a.getByText(/Application started for/)).toBeVisible();
    // Tier denial (Bronze school).
    await pick(a, "bridge-school", "Docs Bronze School");
    await pick(a, "bridge-student", "Docs Bronze Student");
    await a.selectOption("#bridge-university", { index: 1 });
    await a.fill("#bridge-intake", "Fall 2027");
    await a.getByRole("button", { name: "Start application" }).click();
    await a.waitForTimeout(1200);
    await say(a, "bronze application");
    await shoot(a, ADM, "34-school-application-tier-denied.png", { ...opts, element: card(a, "Start an Overseas application for a School student") });
    await a.reload();
    console.log(`VERIFY applications tables: ${(await main(a)).slice(0, 900)}`);
    await shoot(a, ADM, "35-linked-applications.png", { ...opts, center: a.getByRole("heading", { name: "Linked applications" }) });
    await f.ctx.close();
  }
  // Counselor view + U15 (does the school-linked application show in the counselor's applications?).
  {
    const f = await fresh(browser);
    const c = f.page;
    await signIn(c, "counselor@edusphere.local", "seed", /\/overseas\/counselor\//);
    await c.goto("/overseas/counselor/school-applications");
    console.log(`VERIFY counselor school-applications: ${(await main(c)).slice(0, 500)}`);
    await shoot(c, ADM, "36-counselor-school-applications.png", opts);
    await c.goto("/overseas/counselor/applications");
    console.log(`VERIFY U15 counselor applications: ${(await main(c)).slice(0, 800)}`);
    await f.ctx.close();
  }

  // ===== RPT-006 Global education (Coordinator, Principal) =====
  {
    const f = await fresh(browser);
    const q = f.page;
    await signIn(q, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
    await q.goto("/school/coordinator/global-education");
    await expect(q.getByRole("heading", { name: "Global education" })).toBeVisible();
    console.log(`VERIFY CO global ed: ${(await main(q)).slice(0, 900)}`);
    await shoot(q, RPT, "10-global-education-funnel.png", opts);
    await shoot(q, RPT, "11-global-education-students.png", { ...opts, center: q.getByRole("heading", { name: "Students" }) });
    await q.selectOption("#pipeline-grade", { index: 2 });
    await q.getByRole("button", { name: "Show" }).click();
    await q.waitForTimeout(1000);
    console.log(`VERIFY grade filter: ${(await main(q)).slice(0, 300)}`);
    await f.ctx.close();
  }
  {
    const f = await fresh(browser);
    await signIn(f.page, "school.principal@edusphere.local", "seed", /\/school\/principal\//);
    await f.page.goto("/school/principal/global-education");
    console.log(`VERIFY PR global ed: ${(await main(f.page)).slice(0, 300)}`);
    await shoot(f.page, RPT, "12-global-education-principal.png", opts);
    await f.ctx.close();
  }

  school.pathway = { applications: ["Ananya (Sunrise)", "Arjun (Sunrise)"], psych: "Ananya Aptitude Test (completed with results)" };
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
