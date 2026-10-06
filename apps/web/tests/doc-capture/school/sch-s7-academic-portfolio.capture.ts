import { readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S7 (docs/school-crm/documentation-plan.md): DOC-SCH-ACAD-001..007, DOC-SCH-PORT-001..005. Runs after sch-s6.
const AT = "academic-team";
const PF = "portfolio";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").first().innerText()).replace(/\s+/g, " ");
const card = (p: Page, heading: string | RegExp) => p.locator(".card, .action-card, section, details").filter({ has: p.getByRole("heading", { name: heading }) }).last();

async function fresh(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}

// SearchableSelect: type, then pick the first matching option.
async function pick(p: Page, inputId: string, text: string) {
  await p.fill(`#${inputId}`, text);
  await p.getByRole("listbox").getByRole("option", { name: new RegExp(text) }).first().click();
}

async function uploadResult(p: Page, r: { student: string; year: string; term: string; subject: string; max: string; got: string; grade?: string; remarks?: string }, shotForm?: string) {
  await pick(p, "result-student", r.student);
  await p.fill("#result-year", r.year);
  await p.fill("#result-term", r.term);
  await p.fill("#result-subject", r.subject);
  await p.fill("#result-max", r.max);
  await p.fill("#result-obtained", r.got);
  if (r.grade) await p.fill("#result-grade", r.grade);
  if (r.remarks) await p.fill("#result-remarks", r.remarks);
  if (shotForm) await shoot(p, AT, shotForm, { ...opts, element: card(p, "Upload a result") });
  await p.getByRole("button", { name: "Save as Draft" }).click();
}

test("School CRM S7 academic team and digital portfolio", async ({ browser }) => {
  test.setTimeout(900_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));
  const YEAR = "2026-27";

  // ===== Academic Team member 1 (Divya): dashboard, progress, uploads =====
  const a1 = await fresh(browser);
  const p = a1.page;
  await signIn(p, "school.academic1@edusphere.local", "seed", /\/school\/academic-team\//);
  await expect(p.getByRole("heading", { name: "Portfolio progress" })).toBeVisible();
  console.log(`VERIFY AT dashboard headings: ${JSON.stringify(await p.locator("main h2, main h3, main summary").allInnerTexts())}`);
  await shoot(p, AT, "01-dashboard.png", opts);
  await shoot(p, AT, "02-portfolio-progress.png", { ...opts, element: card(p, "Portfolio progress") });

  await uploadResult(p, { student: "Docs Student Arjun", year: YEAR, term: "Term 1", subject: "Mathematics", max: "100", got: "92", grade: "A1", remarks: "Excellent problem solving." }, "03-upload-result-form.png");
  const draft = p.getByText("Mathematics result saved as Draft.");
  await expect(draft).toBeVisible();
  await shoot(p, AT, "04-result-saved-as-draft.png", { ...opts, center: draft });
  await uploadResult(p, { student: "Docs Student Meera", year: YEAR, term: "Term 1", subject: "Science", max: "100", got: "32", grade: "E", remarks: "Needs support with lab work." });
  await expect(p.getByText("Science result saved as Draft.")).toBeVisible();
  await uploadResult(p, { student: "Docs Student Arjun", year: YEAR, term: "Term 1", subject: "English", max: "100", got: "74", grade: "B1" });
  await expect(p.getByText("English result saved as Draft.")).toBeVisible();
  // U5: subject longer than 80 characters.
  await uploadResult(p, { student: "Docs Student Arjun", year: YEAR, term: "Term 1", subject: "S".repeat(90), max: "100", got: "50" });
  await p.waitForTimeout(1500);
  await say(p, "U5 long subject");
  // Marks above maximum on the single form.
  await p.reload();
  await uploadResult(p, { student: "Docs Student Dev", year: YEAR, term: "Term 1", subject: "History", max: "50", got: "75" });
  await p.waitForTimeout(1500);
  await say(p, "marks above max");
  await p.reload();
  console.log(`VERIFY results table (uploader): ${(await card(p, "Results").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await shoot(p, AT, "05-results-uploader-view.png", { ...opts, element: card(p, "Results") });

  // ===== Academic Team member 2 (Suresh): verify + publish =====
  {
    const f = await fresh(browser);
    const q = f.page;
    await signIn(q, "school.academic2@edusphere.local", "seed", /\/school\/academic-team\//);
    const results = card(q, "Results");
    await shoot(q, AT, "06-results-verify-button.png", { ...opts, element: results });
    const who: Record<string, string> = { Mathematics: "Docs Student Arjun", Science: "Docs Student Meera", English: "Docs Student Arjun" };
    const rowOf = (subj: string) => results.getByRole("row", { name: new RegExp(`${who[subj]} ${subj} \\(`) });
    for (const subj of ["Mathematics", "Science", "English"]) {
      await rowOf(subj).getByRole("button", { name: "Verify" }).click();
      await expect(q.getByText("Result verified.")).toBeVisible();
    }
    await shoot(q, AT, "07-result-verified.png", { ...opts, center: q.getByText("Result verified.") });
    for (const subj of ["Mathematics", "Science"]) {
      await rowOf(subj).getByRole("button", { name: "Publish" }).click();
      await expect(q.getByText("Result published.")).toBeVisible();
    }
    await say(q, "published");
    await shoot(q, AT, "08-result-published.png", { ...opts, element: results });
    await f.ctx.close();
  }
  await p.reload();
  console.log(`VERIFY results after (uploader): ${(await card(p, "Results").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);

  // ===== ACAD-004 bulk results =====
  const tpl = await (await p.request.get("/api/v1/school/academic-team/results/bulk-template")).text();
  const lines = tpl.replace(/^﻿/, "").split(/\r?\n/).filter(Boolean);
  const header = lines[0].split(",");
  console.log(`VERIFY results template header: ${lines[0]} (rows ${lines.length - 1})`);
  const rowFor = (name: string) => lines.find((l) => l.includes(name))!.split(",");
  const fill = (name: string, v: Record<string, string>) => { const r = rowFor(name); header.forEach((c, i) => { if (v[c] !== undefined) r[i] = v[c]; }); return r.join(","); };
  const csv = [
    lines[0],
    fill("Docs Student Dev", { academic_year: YEAR, term: "Term 1", subject: "Mathematics", max_marks: "100", marks_obtained: "88", grade: "A2" }),
    fill("Docs Student Nisha", { academic_year: YEAR, term: "Term 1", subject: "Mathematics", max_marks: "100", marks_obtained: "120" }),
    fill("Docs Student Arjun", { academic_year: YEAR, term: "Term 1", subject: "Mathematics", max_marks: "100", marks_obtained: "90" }),
  ].join("\n");
  const csvPath = path.join(os.tmpdir(), "docs-results.csv");
  writeFileSync(csvPath, csv);
  const bulk = p.locator("details").filter({ hasText: "Bulk entry — results (CSV)" });
  await bulk.locator("summary").first().click();
  await shoot(p, AT, "09-bulk-results-panel.png", { ...opts, center: bulk.locator("summary").first() });
  await bulk.locator('input[type="file"]').setInputFiles(csvPath);
  await bulk.getByRole("button", { name: /Upload/ }).click();
  await expect(bulk.getByRole("heading", { name: "Upload result" })).toBeVisible({ timeout: 60_000 });
  console.log(`VERIFY bulk results: ${(await bulk.innerText()).replace(/\s+/g, " ").slice(-700)}`);
  await shoot(p, AT, "10-bulk-results-report.png", { ...opts, center: bulk.getByRole("heading", { name: "Upload result" }) });

  // ===== ACAD-005 test preparation =====
  await p.reload();
  await pick(p, "testprep-student", "Docs Student Ananya");
  await p.selectOption("#testprep-type", { label: "IELTS" });
  await p.fill("#testprep-target", "7.0");
  await shoot(p, AT, "11-test-prep-start.png", { ...opts, center: p.locator("#testprep-target") });
  await p.getByRole("button", { name: "Start preparation" }).click();
  await expect(p.getByText("IELTS preparation started.")).toBeVisible();
  await p.getByLabel("Actual score for Docs Student Ananya").fill("7.5");
  await p.getByRole("row", { name: /Docs Student Ananya/ }).getByRole("button", { name: "Record score" }).click();
  const recorded = p.getByText("Result recorded.");
  await expect(recorded).toBeVisible();
  await shoot(p, AT, "12-test-prep-score-recorded.png", { ...opts, center: recorded });

  // ===== ACAD-006 foreign language =====
  await pick(p, "language-student", "Docs Student Ananya");
  await p.fill("#language-name", "German");
  await p.fill("#language-level", "A1");
  await p.getByRole("button", { name: "Start classes" }).click();
  await expect(p.getByText("German classes started.")).toBeVisible();
  await shoot(p, AT, "13-language-started.png", { ...opts, center: p.getByText("German classes started.") });
  await p.getByRole("row", { name: /Docs Student Ananya.*German/ }).getByRole("button", { name: "Mark certified" }).click();
  const cert = p.getByText("Marked certified.");
  await expect(cert).toBeVisible();
  await shoot(p, AT, "14-language-certified.png", { ...opts, center: cert });

  // ===== ACAD-007 bulk test prep (one bad row) =====
  const tp = await (await p.request.get("/api/v1/school/academic-team/test-prep-records/bulk-template")).text();
  const tpl2 = tp.replace(/^﻿/, "").split(/\r?\n/).filter(Boolean);
  const h2 = tpl2[0].split(",");
  const fill2 = (name: string, v: Record<string, string>) => { const r = tpl2.find((l) => l.includes(name))!.split(","); h2.forEach((c, i) => { if (v[c] !== undefined) r[i] = v[c]; }); return r.join(","); };
  const tpCsv = [tpl2[0], fill2("Docs Student Sara", { test_type: "sat", target_score: "1400" }), fill2("Docs Student Riya", { test_type: "toefl" })].join("\n");
  const tpPath = path.join(os.tmpdir(), "docs-testprep.csv");
  writeFileSync(tpPath, tpCsv);
  const bulk2 = p.locator("details").filter({ hasText: "Bulk entry — test preparation (CSV)" });
  await bulk2.locator("summary").first().click();
  await bulk2.locator('input[type="file"]').setInputFiles(tpPath);
  await bulk2.getByRole("button", { name: /Upload/ }).click();
  await expect(bulk2.getByRole("heading", { name: "Upload result" })).toBeVisible({ timeout: 60_000 });
  console.log(`VERIFY bulk test prep: ${(await bulk2.innerText()).replace(/\s+/g, " ").slice(-500)}`);
  await shoot(p, AT, "15-bulk-test-prep-report.png", { ...opts, center: bulk2.getByRole("heading", { name: "Upload result" }) });

  // ===== PORT-001..005 on Aarav's portfolio (Academic Team) =====
  await p.reload();
  const studentsCard = card(p, "Students");
  console.log(`VERIFY AT students directory: ${(await studentsCard.innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
  await studentsCard.getByRole("link", { name: "Aarav Mehta" }).click();
  await expect(p.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();
  await shoot(p, PF, "01-portfolio-overview.png", { ...opts, center: p.getByRole("heading", { name: "Digital Portfolio" }) });

  // PORT-002 add / edit / delete
  await p.click("#pf-add-btn-award");
  await p.fill("#pf-title", "Science Olympiad Gold Medal");
  await p.fill("#pf-organization", "National Science Foundation of India");
  await p.fill("#pf-date-from", "2026-08-20");
  await p.fill("#pf-description", "Ranked first in the state round.");
  await shoot(p, PF, "02-add-entry-form.png", { ...opts, center: p.locator("#pf-title") });
  await p.click("#pf-save-btn");
  await expect(p.getByText("Award added.")).toBeVisible();
  await shoot(p, PF, "03-entry-added.png", { ...opts, center: p.getByText("Award added.") });
  await p.click("#pf-add-btn-project");
  await p.fill("#pf-title", "Solar Water Heater Model");
  await p.fill("#pf-date-from", "2026-09-10");
  await p.fill("#pf-date-to", "2026-09-01");
  await p.click("#pf-save-btn");
  await p.waitForTimeout(1200);
  await say(p, "end before start");
  await shoot(p, PF, "04-entry-date-error.png", { ...opts, center: p.locator("#pf-title") });
  await p.fill("#pf-date-to", "2026-09-30");
  await p.click("#pf-save-btn");
  await expect(p.getByText("Project added.")).toBeVisible();
  await p.getByRole("button", { name: "Edit Solar Water Heater Model" }).click();
  await p.fill("#pf-title", "Solar Water Heater (working model)");
  await p.click("#pf-save-btn");
  await expect(p.getByText("Project updated.")).toBeVisible();
  await p.getByRole("button", { name: "Delete Solar Water Heater (working model)" }).click();
  const confirmDel = p.getByRole("button", { name: "Confirm delete Solar Water Heater (working model)" });
  await expect(confirmDel).toBeVisible();
  await shoot(p, PF, "05-delete-confirm.png", { ...opts, center: confirmDel });
  await confirmDel.click();
  await expect(p.getByText("Project deleted.")).toBeVisible();

  // PORT-003 Skill India
  await p.click("#pf-add-btn-certification");
  await p.fill("#pf-title", "Data Entry Operator");
  await p.check("#pf-skill-india");
  await p.selectOption("#pf-cert-status", { label: "Certified" });
  await p.click("#pf-save-btn");
  await p.waitForTimeout(800);
  await say(p, "skill india missing");
  await shoot(p, PF, "06-skill-india-errors.png", { ...opts, center: p.locator("#pf-cert-status") });
  await p.fill("#pf-cert-number", "SI-2026-0042117");
  await p.fill("#pf-cert-issued", "2026-09-15");
  await p.fill("#pf-organization", "NSDC");
  await shoot(p, PF, "07-skill-india-form.png", { ...opts, center: p.locator("#pf-cert-number") });
  await p.click("#pf-save-btn");
  await expect(p.getByText("Certification added.")).toBeVisible();
  await shoot(p, PF, "08-skill-india-saved.png", { ...opts, center: p.getByText("Certification added.") });

  // PORT-004 internship + certificate (Sunrise is Platinum)
  await p.click("#pf-add-btn-internship");
  await p.fill("#pf-title", "Junior Data Analyst Intern");
  await p.fill("#pf-organization", "Docs Analytics Pvt Ltd");
  await p.fill("#pf-date-from", "2026-05-01");
  await p.fill("#pf-date-to", "2026-06-15");
  await p.fill("#pf-mentor", "Docs Mentor Rao");
  await p.fill("#pf-mentor-role", "Lead Analyst");
  await p.selectOption("#pf-completion", { label: "Completed" });
  await p.fill("#pf-attendance", "95");
  await p.fill("#pf-skills", "Excel, SQL basics");
  await shoot(p, PF, "09-internship-form.png", { ...opts, center: p.locator("#pf-mentor") });
  await p.click("#pf-save-btn");
  await expect(p.getByText("Internship added.")).toBeVisible();
  const big = path.join(os.tmpdir(), "docs-cert-big.pdf");
  writeFileSync(big, Buffer.concat([Buffer.from("%PDF-1.4\n"), Buffer.alloc(6 * 1024 * 1024, 32)]));
  const small = path.join(os.tmpdir(), "docs-cert.pdf");
  writeFileSync(small, "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");
  const certInput = p.getByLabel(/Upload certificate \(PDF, JPEG or PNG, up to 5 MB\)/);
  await certInput.setInputFiles(big);
  await p.waitForTimeout(800);
  await say(p, "cert too big");
  await shoot(p, PF, "10-certificate-too-big.png", { ...opts, center: certInput });
  await certInput.setInputFiles(small);
  await expect(p.getByText("Certificate saved.")).toBeVisible({ timeout: 20_000 });
  await shoot(p, PF, "11-certificate-saved.png", { ...opts, center: p.getByText("Certificate saved.") });

  // PORT-005 personal statement
  await p.click("#pf-statement-edit-btn");
  await p.fill("#pf-statement-textarea", "I enjoy building things that solve everyday problems, and I want to study mechanical engineering abroad.");
  await p.click("#pf-statement-save-btn");
  await expect(p.getByText("Personal statement saved.")).toBeVisible();
  await shoot(p, PF, "12-personal-statement-saved.png", { ...opts, center: p.getByText("Personal statement saved.") });
  console.log(`VERIFY portfolio after: ${(await card(p, "Digital Portfolio").innerText()).replace(/\s+/g, " ").slice(0, 400)}`);
  // Centre on the entry sections, not the heading, so the shot differs from 12.
  await shoot(p, PF, "13-portfolio-complete-view.png", { ...opts, center: p.locator("#pf-add-btn-certification") });
  await a1.ctx.close();

  // ===== Bronze school: portfolio locked by tier =====
  {
    const f = await fresh(browser);
    const b = f.page;
    await signIn(b, school.schools.bronze.email, "test", /\/school\/coordinator\//);
    await b.goto("/school/coordinator/students");
    await b.fill("#new-full-name", "Docs Bronze Student");
    await b.getByRole("button", { name: "Add student" }).click();
    await expect(b.getByText(/Docs Bronze Student added to the roster/)).toBeVisible();
    await b.getByRole("row", { name: /Docs Bronze Student/ }).getByRole("link", { name: "Profile & timeline" }).click();
    await expect(b.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();
    await b.click("#pf-add-btn-award");
    await b.fill("#pf-title", "Docs award");
    await b.click("#pf-save-btn");
    await b.waitForTimeout(1200);
    await say(b, "bronze portfolio");
    await shoot(b, PF, "14-portfolio-tier-denied.png", { ...opts, center: b.locator("#pf-title") });
    await b.locator("#pf-title").press("Escape").catch(() => {});
    await b.reload();
    await shoot(b, PF, "15-internships-platinum-only.png", { ...opts, center: b.getByText(/Internship tracking is part of the Platinum partnership/) });
    await f.ctx.close();
  }

  // ===== U14: assigned Teacher edits a portfolio =====
  {
    const f = await fresh(browser);
    const t = f.page;
    await signIn(t, "docs.teacher.a@example.test", "test", /\/school\/teacher\//);
    const students = await (await t.request.get("/api/v1/school/students")).json();
    const arjun = students.find((s: { full_name: string }) => s.full_name === "Docs Student Arjun");
    await t.goto(`/school/teacher/students/${arjun.id}`);
    await t.click("#pf-add-btn-skill");
    await t.fill("#pf-title", "Spreadsheet basics");
    await t.click("#pf-save-btn");
    await t.waitForTimeout(1500);
    await say(t, "teacher portfolio");
    await shoot(t, PF, "16-teacher-adds-skill.png", { ...opts, center: t.getByRole("heading", { name: "Digital Portfolio" }) });
    await f.ctx.close();
  }

  school.academic = { published: ["Mathematics (Arjun 92)", "Science (Meera 32)"], verifiedOnly: ["English"], portfolio: "Aarav Mehta" };
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
