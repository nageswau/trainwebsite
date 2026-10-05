import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { shoot, signIn, toTop } from "./shoot";

// S5 (docs/documentation-plan.md): DOC-APP-001..005 and DOC-TASK-001..002, in "EduSphere Partner Agency".
// Runs after s4-students (needs Neha Sharma assigned to Asha Staff and the paging students).
const APP = "applications";
const TASK = "tasks";
const staffEmail = (key: string) => JSON.parse(readFileSync(String(process.env.DOCS_STAFF_FILE), "utf8"))[key] as string;

const day = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
async function selectByText(select: Locator, text: string) {
  const value = await select.locator("option", { hasText: text }).first().getAttribute("value");
  await select.selectOption(value ?? "");
}
async function pick(page: Page, combo: Locator, text: string) {
  await combo.fill(text);
  await page.getByRole("option", { name: new RegExp(`^${text}`) }).first().click();
}

type NewApp = { student: string; university: string; course?: boolean; intake: string; id?: string; submitted?: string; appDeadline?: string; offerDeadline?: string };
async function fillApp(page: Page, a: NewApp) {
  await pick(page, page.getByRole("combobox", { name: "Linked student" }), a.student);
  await selectByText(page.getByLabel("University (required)"), a.university);
  if (a.course) {
    const course = page.getByLabel("Course (optional)");
    const v = await course.locator("option").nth(1).getAttribute("value");
    if (v) await course.selectOption(v);
  }
  await page.getByLabel("Intake (required)").fill(a.intake);
  if (a.id) await page.getByLabel("Application ID").first().fill(a.id);
  if (a.submitted) await page.getByLabel("Submitted on").first().fill(a.submitted);
  if (a.appDeadline) await page.getByLabel("Application deadline").first().fill(a.appDeadline);
  if (a.offerDeadline) await page.getByLabel("Offer deadline").first().fill(a.offerDeadline);
}
async function createApp(page: Page, a: NewApp) {
  await fillApp(page, a);
  await page.getByRole("button", { name: "Create application" }).click();
  await expect(page.getByText("Application created.")).toBeVisible();
}
const view = (page: Page, student: string, uni: string) => page.getByRole("button", { name: `View ${student} — ${uni}` });

test("S5 applications and tasks", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  const m = await ctx.newPage();
  m.on("dialog", (d) => d.accept());
  await signIn(m, "agent@edusphere.local");
  await m.goto("/overseas/agent/applications");

  // --- DOC-APP-002 create (form, validation, success, duplicate) ---
  await shoot(m, APP, "01-applications-page.png");
  const manchester: NewApp = { student: "Neha Sharma", university: "University of Manchester", course: true, intake: "Sep 2027", id: "MAN-2027-0142", appDeadline: day(3) };
  await fillApp(m, { ...manchester, submitted: day(30) });
  await m.getByRole("button", { name: "Create application" }).click();
  await m.waitForTimeout(1200);
  await say(m, "APP-002 future submitted date");
  await shoot(m, APP, "03-create-future-date.png");
  await m.getByLabel("Submitted on").first().fill("");
  await toTop(m.getByRole("heading", { name: "Create application" }));
  await shoot(m, APP, "02-create-form.png");
  await m.getByRole("button", { name: "Create application" }).click();
  await expect(m.getByText("Application created.")).toBeVisible();
  await shoot(m, APP, "04-create-success.png");
  await fillApp(m, manchester);
  await m.getByRole("button", { name: "Create application" }).click();
  await expect(m.getByText("An application for this university/course already exists")).toBeVisible();
  await toTop(m.getByLabel("Course (optional)"), 120);
  await shoot(m, APP, "05-create-duplicate.png");
  await m.reload();

  await createApp(m, { student: "Neha Sharma", university: "Monash University", intake: "Feb 2028", id: "MON-88231", submitted: day(-2), appDeadline: day(1) });
  await createApp(m, { student: "Aarav Mehta", university: "University of Birmingham", intake: "Sep 2027", id: "BHM-7781" });
  await createApp(m, { student: "Diya Nair", university: "Technical University of Munich", intake: "Oct 2027" });
  await createApp(m, { student: "Ishaan Gupta", university: "University of Waterloo", intake: "Sep 2027" });
  await createApp(m, { student: "Kavya Reddy", university: "University of Alberta", intake: "Jan 2028", appDeadline: day(0) });

  // --- DOC-APP-005 change status / withdraw ---
  await m.reload();
  await view(m, "Aarav Mehta", "University of Birmingham").click();
  await selectByText(m.getByLabel("Move to"), "Offer");
  await m.getByLabel("Note (optional)").fill("Offer email received from Birmingham admissions.");
  await toTop(m.getByRole("heading", { name: "Change status" }));
  await shoot(m, APP, "11-change-status.png");
  await m.getByRole("button", { name: "Update status" }).click();
  await expect(m.getByText("Status updated to Offer.")).toBeVisible();
  await m.getByRole("button", { name: "Close" }).first().click();
  await view(m, "Diya Nair", "Technical University of Munich").click();
  await selectByText(m.getByLabel("Move to"), "Visa documentation");
  await m.getByRole("button", { name: "Update status" }).click();
  await expect(m.getByText("Status updated to Visa documentation.")).toBeVisible();
  await m.getByRole("button", { name: "Close" }).first().click();
  await view(m, "Ishaan Gupta", "University of Waterloo").click();
  await m.getByRole("button", { name: "Withdraw application" }).click();
  await toTop(m.getByRole("heading", { name: "Change status" }));
  await shoot(m, APP, "12-withdraw-confirm.png");
  await m.getByRole("button", { name: "Yes, withdraw" }).click();
  await expect(m.getByText("Application withdrawn.")).toBeVisible();
  await expect(m.getByText("This application is withdrawn, so it can no longer be changed.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: /Ishaan Gupta — University of Waterloo/ }).last());
  await shoot(m, APP, "13-withdrawn-read-only.png");
  await m.getByRole("button", { name: "Close" }).first().click();

  // --- DOC-APP-003 edit; DOC-APP-004 detail ---
  await view(m, "Neha Sharma", "University of Manchester").click();
  await m.getByRole("button", { name: "Edit", exact: true }).click();
  await m.getByLabel("Offer deadline").last().fill(day(45));
  await m.getByLabel("Next action").fill("Collect SOP draft and two reference letters");
  await toTop(m.getByText("To change university, withdraw and create a new application."), 160);
  await shoot(m, APP, "09-edit-form.png");
  await m.getByRole("button", { name: "Save", exact: true }).click();
  await expect(m.getByText("Saved.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: /Neha Sharma — University of Manchester/ }).last());
  await shoot(m, APP, "10-application-detail.png", { fullPage: false });
  await m.getByRole("button", { name: "Close" }).first().click();

  // --- DOC-APP-001 list and filters ---
  await toTop(m.getByRole("heading", { name: "All applications" }));
  await shoot(m, APP, "06-list-all.png");
  for (const [status, file] of [["draft", "07-filter-draft.png"], ["submitted", "07-filter-submitted.png"], ["offer", "07-filter-offer.png"], ["visa", "07-filter-visa.png"], ["withdrawn", "07-filter-withdrawn.png"], ["enrolled", "08-filter-empty.png"]]) {
    await m.goto(`/overseas/agent/applications?status=${status}`);
    await m.waitForTimeout(800);
    const heading = m.getByRole("heading", { level: 4 }).filter({ hasText: /applications|Draft|Submitted|Offer|Visa|Withdrawn|Enrolled/i }).first();
    if (await heading.count()) await toTop(heading);
    console.log(`VERIFY APP-001 ${status}: ${(await m.locator("main").innerText()).split("Create application").pop()?.replace(/\s+/g, " ").slice(0, 300)}`);
    await shoot(m, APP, file);
  }

  // --- DOC-TASK-001/002 tasks ---
  await m.goto("/overseas/agent/tasks");
  await expect(m.getByText("No open tasks.")).toBeVisible();
  await m.getByRole("button", { name: "New task" }).first().click();
  await m.getByRole("button", { name: "Add task" }).click();
  await expect(m.getByText("Title is required.")).toBeVisible();
  await shoot(m, TASK, "03-task-validation.png");
  const task = async (student: string, title: string, due: string, app?: string, notes?: string, shot?: string) => {
    await pick(m, m.getByRole("combobox", { name: "Student" }), student);
    await m.getByLabel("Title").fill(title);
    await m.getByLabel("Due").fill(due);
    if (app) await selectByText(m.getByLabel("Application (optional)"), app);
    if (notes) await m.getByLabel("Notes (optional)").fill(notes);
    if (shot) await shoot(m, TASK, shot);
    await m.getByRole("button", { name: "Add task" }).click();
    await expect(m.getByText(`“${title}” added.`)).toBeVisible();
  };
  await task("Neha Sharma", "Collect IELTS scorecard", `${day(1)}T17:00`, "University of Manchester", "Ask for the TRF number as well.", "02-new-task-form.png");
  await m.getByRole("button", { name: "New task" }).first().click();
  await task("Aarav Mehta", "Call Aarav about the offer conditions", `${day(-1)}T11:00`, undefined, undefined, "04-new-task-past-due.png");
  await m.getByRole("button", { name: "New task" }).first().click();
  await task("Diya Nair", "Send visa checklist to Diya", `${day(2)}T10:00`);
  await m.getByRole("button", { name: "New task" }).first().click();
  await task("Kavya Reddy", "Book counseling slot", `${day(4)}T15:30`);
  await m.reload();
  await shoot(m, TASK, "01-tasks-open.png");
  await m.getByRole("button", { name: "Mark “Send visa checklist to Diya” done" }).click();
  await expect(m.getByText("“Send visa checklist to Diya” marked done.")).toBeVisible();
  await m.getByRole("button", { name: "Cancel “Book counseling slot”" }).click();
  await shoot(m, TASK, "06-cancel-task-confirm.png");
  await m.getByRole("button", { name: "Confirm cancel" }).click();
  await expect(m.getByText("“Book counseling slot” cancelled.")).toBeVisible();
  for (const [v, file] of [["overdue", "05-tasks-overdue.png"], ["done", "07-tasks-done.png"], ["cancelled", "08-tasks-cancelled.png"], ["all", "09-tasks-all.png"]]) {
    await m.getByRole("link", { name: v.charAt(0).toUpperCase() + v.slice(1), exact: true }).click();
    await m.waitForTimeout(800);
    await shoot(m, TASK, file);
  }
  await ctx.close();

  // --- Staff views ---
  const sctx = await browser.newContext();
  const s = await sctx.newPage();
  await signIn(s, staffEmail("a"), "test");
  await s.goto("/overseas/agent/applications");
  await expect(view(s, "Neha Sharma", "University of Manchester")).toBeVisible();
  await toTop(s.getByRole("heading", { name: "All applications" }));
  await shoot(s, APP, "14-staff-applications.png");
  await s.goto("/overseas/agent/tasks");
  await shoot(s, TASK, "10-staff-tasks.png");
  await sctx.close();
});
