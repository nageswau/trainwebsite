import { readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S4 (docs/school-crm/documentation-plan.md): DOC-SCH-STU-001..008. Runs after sch-s3 on the same DB.
const STU = "students";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const body = async (page: Page) => (await page.locator("body").innerText()).replace(/\s+/g, " ");
const card = (p: Page, heading: string | RegExp) => p.locator(".card, .action-card, section").filter({ has: p.getByRole("heading", { name: heading }) }).last();

async function fresh(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}

async function fillStudent(p: Page, s: Record<string, string>) {
  const set = async (id: string, v?: string) => { if (v !== undefined) await p.fill(`#new-${id}`, v); };
  await set("full-name", s.name);
  await set("dob", s.dob);
  if (s.gender) await p.selectOption("#new-gender", { label: s.gender });
  await set("grade", s.grade);
  await set("grade-level", s.level);
  await set("section", s.section);
  await set("roll", s.roll);
  if (s.teacher) await p.selectOption("#new-teacher", { label: s.teacher });
  await set("mobile", s.mobile);
  await set("city", s.city);
  await set("parent-name", s.parentName);
  await set("parent-email", s.parentEmail);
  await set("subjects", s.subjects);
  await set("career_interests", s.careers);
  await set("preferred_countries", s.countries);
  await set("preferred_courses", s.courses);
  if (s.abroad) await p.selectOption("#new-global", { label: s.abroad });
}

const csvCell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

test("School CRM S4 students and roster", async ({ browser }) => {
  test.setTimeout(600_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));

  // --- STU-001 empty roster (new school) ---
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, school.schools.platinum2.email, "test", /\/school\/coordinator\//);
    await page.goto("/school/coordinator/students");
    await expect(page.getByRole("heading", { name: "Student roster" })).toBeVisible();
    console.log(`VERIFY empty roster: ${(await body(page)).slice(0, 400)}`);
    await shoot(page, STU, "02-roster-empty.png", opts);
    await ctx.close();
  }

  const co = await fresh(browser);
  const p = co.page;
  await signIn(p, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
  await p.goto("/school/coordinator/students");
  await expect(p.getByRole("heading", { name: "Student roster" })).toBeVisible();
  await shoot(p, STU, "01-roster.png", opts);

  // --- STU-002 add one student (new parent -> invite) ---
  await fillStudent(p, {
    name: "Docs Student Ananya", dob: "2011-07-14", gender: "Female", grade: "Grade 9", level: "9", section: "A", roll: "1",
    teacher: "Docs Teacher A", mobile: "+91 98200 11111", city: "Hyderabad", parentName: "Docs Parent Two", parentEmail: "docs.parent2@example.test",
    subjects: "Maths, Physics", careers: "Engineering, Design", countries: "Germany, Canada", courses: "Mechanical Engineering", abroad: "Yes",
  });
  await shoot(p, STU, "03-add-student-filled.png", { ...opts, element: card(p, "Add one student") });
  await p.getByRole("button", { name: "Add student" }).click();
  const added = p.getByText(/Docs Student Ananya added to the roster\./);
  await expect(added).toBeVisible({ timeout: 20_000 });
  await say(p, "add student");
  await shoot(p, STU, "04-add-student-success.png", { ...opts, center: added });
  // Existing parent account -> linked immediately.
  await fillStudent(p, { name: "Docs Student Vihaan", grade: "Grade 10", level: "10", section: "A", roll: "1", teacher: "Docs Teacher A", parentEmail: "school.parent@edusphere.local" });
  await p.getByRole("button", { name: "Add student" }).click();
  await expect(p.getByText(/Docs Student Vihaan added to the roster\./)).toBeVisible({ timeout: 20_000 });
  await say(p, "add student existing parent");
  // Roll-number clash.
  await fillStudent(p, { name: "Docs Student Clash", grade: "Grade 9", level: "9", section: "A", roll: "1" });
  await p.getByRole("button", { name: "Add student" }).click();
  const clash = p.getByText(/already used in this grade and section/);
  await expect(clash).toBeVisible();
  await say(p, "roll clash");
  await shoot(p, STU, "05-add-student-roll-conflict.png", { ...opts, center: clash });
  // Non-parent email.
  await p.fill("#new-roll", "2");
  await p.fill("#new-parent-email", "school.teacher@edusphere.local");
  await p.getByRole("button", { name: "Add student" }).click();
  await expect(p.getByText(/is not a Parent|not a Parent/)).toBeVisible();
  await say(p, "non-parent email");
  // U5: over-length full name (no client limit).
  await p.reload();
  await fillStudent(p, { name: "Docs " + "X".repeat(170) });
  await p.getByRole("button", { name: "Add student" }).click();
  await p.waitForTimeout(2500);
  await say(p, "U5 long name");
  // U4: the documented /students/new route.
  await p.goto("/school/coordinator/students/new");
  console.log(`VERIFY U4 /students/new: ${(await body(p)).slice(0, 300)}`);

  // --- STU-003 edit ---
  await p.goto("/school/coordinator/students");
  await p.getByRole("row", { name: /Docs Student Ananya/ }).getByRole("button", { name: "Edit" }).click();
  await expect(p.locator("#edit-section")).toBeVisible();
  await p.fill("#edit-section", "B");
  await shoot(p, STU, "06-edit-student.png", { ...opts, element: card(p, /^Edit /) });
  await p.getByRole("button", { name: "Save changes" }).click();
  const updated = p.getByText(/Student updated\./);
  await expect(updated).toBeVisible();
  await say(p, "edit");
  await shoot(p, STU, "07-edit-student-saved.png", { ...opts, center: updated });

  // --- STU-004 link a parent ---
  await p.getByRole("row", { name: /Kabir Nair/ }).getByRole("button", { name: "Link parent" }).click();
  await p.fill("#link-parent-email", "school.parent@edusphere.local");
  await shoot(p, STU, "08-link-parent-form.png", { ...opts, center: p.locator("#link-parent-email") });
  await p.locator("form").filter({ has: p.locator("#link-parent-email") }).getByRole("button", { name: "Link parent" }).click();
  const linked = p.getByText("Parent linked to this student.");
  await expect(linked).toBeVisible();
  await shoot(p, STU, "09-link-parent-success.png", { ...opts, center: linked });
  await p.getByRole("row", { name: /Kabir Nair/ }).getByRole("button", { name: "Link parent" }).click();
  await p.fill("#link-parent-email", "school.parent@edusphere.local");
  await p.locator("form").filter({ has: p.locator("#link-parent-email") }).getByRole("button", { name: "Link parent" }).click();
  const dup = p.getByText(/already linked to this student/);
  await expect(dup).toBeVisible();
  await say(p, "link duplicate");
  await shoot(p, STU, "10-link-parent-already-linked.png", { ...opts, center: dup });
  await p.fill("#link-parent-email", "school.teacher@edusphere.local");
  await p.locator("form").filter({ has: p.locator("#link-parent-email") }).getByRole("button", { name: "Link parent" }).click();
  await p.waitForTimeout(1500);
  await say(p, "link non-parent");

  // --- STU-005 bulk upload ---
  const tpl = await (await p.request.get("/api/v1/school/students/roster-template")).text();
  console.log(`VERIFY U13 template: ${tpl.replace(/\r?\n/g, " ⏎ ").slice(0, 400)}`);
  const header = tpl.split(/\r?\n/)[0].replace(/^﻿/, "");
  const cols = header.split(",");
  const row = (v: Record<string, string>) => cols.map((c) => csvCell(v[c] ?? "")).join(",");
  const T = "docs.teacher.a@example.test";
  const good = [
    ["Docs Student Arjun", "8", "Grade 8", "A", "11"], ["Docs Student Meera", "8", "Grade 8", "A", "12"],
    ["Docs Student Kabir R", "9", "Grade 9", "A", "13"], ["Docs Student Sara", "10", "Grade 10", "A", "14"],
    ["Docs Student Dev", "11", "Grade 11", "A", "15"], ["Docs Student Nisha", "11", "Grade 11", "A", "16"],
    ["Docs Student Omar", "12", "Grade 12", "A", "17"], ["Docs Student Riya", "12", "Grade 12", "A", "18"],
  ].map(([n, l, g, s, r]) => row({ full_name: n, grade_level: l, grade_or_class: g, section: s, roll_number: r, assigned_teacher_email: T, date_of_birth: "2010-05-01", gender: "male", city: "Hyderabad", subjects: "Maths;English", global_education_interest: "yes", preferred_countries: "UK;Australia" }));
  const csv = [
    header, ...good,
    row({ full_name: "Docs Student No Level", grade_or_class: "Grade 7" }),
    row({ full_name: "Docs Student Label Mismatch", grade_or_class: "Class X", grade_level: "9", section: "C", roll_number: "1" }),
    row({ full_name: "Docs Student Existing Parent", grade_or_class: "Grade 8", grade_level: "8", parent_email: "school.parent@edusphere.local" }),
    row({ full_name: "Docs Bad Date", date_of_birth: "14/07/2011" }),
    row({ full_name: "Docs Bad Teacher", assigned_teacher_email: "nobody@example.test" }),
    row({ full_name: "Docs Bad Parent", parent_email: "school.teacher@edusphere.local" }),
    row({ full_name: "Docs Bad Level", grade_level: "13" }),
    row({ full_name: "Docs Duplicate Roll", grade_or_class: "Grade 8", grade_level: "8", section: "A", roll_number: "11" }),
    row({ full_name: "" , city: "Pune" }),
  ].join("\n");
  const csvPath = path.join(os.tmpdir(), "docs-roster.csv");
  writeFileSync(csvPath, csv);
  await p.goto("/school/coordinator/students/bulk-upload");
  await p.getByText("Column reference").first().click();
  await shoot(p, STU, "11-bulk-template-and-columns.png", opts);
  // With no file chosen the browser's own "required" prompt stops the upload (the page message never shows).
  console.log(`VERIFY file input required: ${await p.locator("#roster-file").evaluate((el) => (el as HTMLInputElement).required)}`);
  await p.setInputFiles("#roster-file", csvPath);
  await p.getByRole("button", { name: "Upload roster" }).click();
  const result = p.getByRole("heading", { name: "Upload result" });
  await expect(result).toBeVisible({ timeout: 60_000 });
  console.log(`VERIFY bulk result: ${(await card(p, "Upload result").innerText()).replace(/\s+/g, " ").slice(0, 1500)}`);
  await shoot(p, STU, "13-bulk-upload-result.png", { ...opts, element: card(p, "Upload result") });

  // --- STU-006 student profile & timeline (Aarav, seeded with history) ---
  const students = await (await p.request.get("/api/v1/school/students")).json();
  const aarav = students.find((s: { full_name: string }) => s.full_name === "Aarav Mehta");
  await p.goto(`/school/coordinator/students/${aarav.id}`);
  await expect(p.getByRole("link", { name: "Open 360° view" })).toBeVisible();
  console.log(`VERIFY CO student page headings: ${JSON.stringify(await p.locator("main h2, main h3, main summary").allInnerTexts())}`);
  await shoot(p, STU, "14-student-profile-header.png", opts);
  await shoot(p, STU, "15-student-journey-timeline.png", { ...opts, center: p.getByRole("heading", { name: "Journey timeline" }) });
  await shoot(p, STU, "16-student-progress-scorecard.png", { ...opts, center: p.getByRole("heading", { name: "Progress scorecard" }) });

  // --- STU-007 photo ---
  const png = path.join(os.tmpdir(), "docs-photo.png");
  {
    // A neutral initials avatar as the test photo (no real person).
    const art = await co.ctx.newPage();
    await art.setViewportSize({ width: 240, height: 240 });
    await art.setContent('<body style="margin:0"><div style="width:240px;height:240px;background:#7aa7d9;display:flex;align-items:center;justify-content:center;font:bold 96px sans-serif;color:#fff">AM</div></body>');
    await art.screenshot({ path: png });
    await art.close();
  }
  const big = path.join(os.tmpdir(), "docs-photo-big.png");
  writeFileSync(big, Buffer.alloc(3 * 1024 * 1024, 7));
  const pdf = path.join(os.tmpdir(), "docs-photo.pdf");
  writeFileSync(pdf, "%PDF-1.4 not a photo");
  const photoInput = p.locator(`#photo-${aarav.id}`);
  await photoInput.setInputFiles(pdf);
  await p.waitForTimeout(1000);
  await say(p, "photo wrong type");
  await photoInput.setInputFiles(big);
  await p.waitForTimeout(1000);
  await say(p, "photo too big");
  await shoot(p, STU, "17-photo-too-big.png", { ...opts, center: photoInput });
  await photoInput.setInputFiles(png);
  await expect(p.getByText("Photo saved.")).toBeVisible({ timeout: 20_000 });
  await shoot(p, STU, "18-photo-saved.png", { ...opts, center: photoInput });
  await p.getByRole("button", { name: "Remove photo" }).click();
  await shoot(p, STU, "19-photo-remove-confirm.png", { ...opts, center: photoInput });
  await p.getByRole("button", { name: "Confirm remove" }).click();
  await expect(p.getByText("Photo removed.")).toBeVisible();
  await say(p, "photo removed");
  // Put a photo back so later sessions show one.
  await p.locator(`#photo-${aarav.id}`).setInputFiles(png);
  await expect(p.getByText("Photo saved.")).toBeVisible({ timeout: 20_000 });

  // --- STU-008 progress report (Coordinator) ---
  const dl = p.waitForEvent("download");
  await p.getByRole("button", { name: "Download progress report (PDF)" }).click();
  const d = await dl;
  console.log(`VERIFY CO report file: ${d.suggestedFilename()}`);
  await expect(p.getByText("Report downloaded.")).toBeVisible();
  await shoot(p, STU, "20-progress-report-downloaded.png", { ...opts, center: p.getByText("Report downloaded.") });
  await co.ctx.close();

  // --- STU-006/008 as Principal and Teacher; STU-008 as Parent ---
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, "school.principal@edusphere.local", "seed", /\/school\/principal\//);
    await page.goto(`/school/principal/students/${aarav.id}`);
    await expect(page.getByRole("link", { name: "Open 360° view" })).toBeVisible();
    console.log(`VERIFY PR student page headings: ${JSON.stringify(await page.locator("main h2, main h3, main summary").allInnerTexts())}`);
    await shoot(page, STU, "21-student-profile-principal.png", opts);
    const dl2 = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download progress report (PDF)" }).click();
    console.log(`VERIFY PR report file: ${(await dl2).suggestedFilename()}`);
    await ctx.close();
  }
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, "school.teacher@edusphere.local", "seed", /\/school\/teacher\//);
    await page.goto(`/school/teacher/students/${aarav.id}`);
    await expect(page.getByRole("link", { name: "Open 360° view" })).toBeVisible();
    console.log(`VERIFY TE student page headings: ${JSON.stringify(await page.locator("main h2, main h3, main summary").allInnerTexts())}`);
    await shoot(page, STU, "22-student-profile-teacher.png", opts);
    const kabir = students.find((s: { full_name: string }) => s.full_name === "Kabir Nair");
    await page.goto(`/school/teacher/students/${kabir.id}`);
    console.log(`VERIFY TE unassigned: ${(await body(page)).slice(0, 200)}`);
    await ctx.close();
  }
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, "school.parent@edusphere.local", "seed", /\/school\/parent\//);
    await page.goto(`/school/parent/children/${aarav.id}`);
    const dl3 = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download progress report (PDF)" }).click();
    console.log(`VERIFY PA report file: ${(await dl3).suggestedFilename()}`);
    await ctx.close();
  }

  school.students = { aarav: aarav.id, added: ["Docs Student Ananya", "Docs Student Vihaan"], parentInvite: "docs.parent2@example.test" };
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
