import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S7 (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-STU-001..003, NOTE-001, TT-001, NOTIF-001, TASK-001,
// ADM-003, ADM-004. Runs after itc-s6b. No payment is recorded (owner I3).
const root = ITC_ROOT;
const A = "docs.itc.a@example.test";
const B = "docs.itc.b@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1800);
const istDate = (days = 0) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);

test("IT Counselor CRM S7 students", async ({ browser }) => {
  test.setTimeout(900_000);

  // ===== IT Admin: ADM-003 assign / change counselor, ADM-004 resume limit, TT-001 weekly slots =====
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  await a.goto("/it/admin/students");
  await settle(a);
  const rowOf = (name: string) => a.locator("tr", { hasText: name }).first();
  const idOf = async (name: string) => {
    const href = await rowOf(name).getByRole("link", { name: "Open" }).getAttribute("href");
    return href!.split("/").pop()!;
  };
  const ids = { arjun: await idOf("Docs IT Lead Arjun"), farah: await idOf("Docs Overseas Student Farah"), esha: await idOf("Docs IT Student Esha") };
  console.log(`IDS ${JSON.stringify(ids)}`);
  const table = a.locator("main .workspace").first();
  await shoot(a, "admin", "20-admin-students.png", { root, element: table });

  const pick = async (form: Locator, who: string) => {
    await form.getByRole("combobox").fill(who.split(" ").pop()!);
    await settle(a, 1200);
    await form.getByRole("option", { name: new RegExp(who) }).first().click();
  };
  // Assign (first assignment: reason optional)
  await rowOf("Docs IT Student Esha").getByRole("button", { name: "Assign counsellor" }).click();
  const af = a.getByRole("form", { name: "Assign counsellor" });
  await pick(af, "Docs IT Counselor A");
  await af.getByLabel("Reason (optional)").fill("Lead was handled by Counselor A");
  await shoot(a, "admin", "21-assign-counselor-form.png", { root, element: rowOf("Docs IT Student Esha") });
  await af.getByRole("button", { name: "Save" }).click();
  await settle(a, 2500);
  await say(a, "ADM-003 assigned");
  // Change (replacing: reason required)
  await rowOf("Docs IT Student Esha").getByRole("button", { name: "Change counsellor" }).click();
  const cf = a.getByRole("form", { name: "Change counsellor" });
  await pick(cf, "Docs IT Counselor B");
  console.log(`VERIFY ADM-003 save disabled without reason: ${await cf.getByRole("button", { name: "Save" }).isDisabled()}`);
  await cf.getByLabel("Reason for the change").fill("Workload balance");
  await shoot(a, "admin", "22-change-counselor-form.png", { root, element: rowOf("Docs IT Student Esha") });
  await cf.getByRole("button", { name: "Save" }).click();
  await settle(a, 2500);
  await say(a, "ADM-003 changed");
  // Finding P11: a dual (Overseas + IT) student cannot be changed here
  await rowOf("Docs Overseas Student Farah").getByRole("button", { name: "Change counsellor" }).click();
  const ff = a.getByRole("form", { name: "Change counsellor" });
  await pick(ff, "Docs IT Counselor B");
  await ff.getByLabel("Reason for the change").fill("Workload balance");
  await ff.getByRole("button", { name: "Save" }).click();
  await settle(a, 2500);
  await say(a, "ADM-003 dual student");
  await shoot(a, "admin", "22b-change-counselor-dual-student.png", { root, element: rowOf("Docs Overseas Student Farah") });
  await ff.getByRole("button", { name: "Cancel" }).click();
  await settle(a, 800);
  console.log(`VERIFY ADM-003 rows: ${await text(table)}`);
  await shoot(a, "admin", "23-counselor-changed.png", { root, element: table });

  // Resume upload limit
  const rl = sec(a, "Resume upload limit");
  await rl.getByLabel("Limit (MB)").fill("11");
  await rl.getByRole("button", { name: "Set limit" }).click();
  await settle(a, 1500);
  await say(a, "ADM-004 invalid");
  await shoot(a, "admin", "24-resume-limit-invalid.png", { root, element: rl });
  await rl.getByLabel("Limit (MB)").fill("8");
  await rl.getByRole("button", { name: "Set limit" }).click();
  await settle(a, 2000);
  await say(a, "ADM-004 saved 8");
  await shoot(a, "admin", "25-resume-limit-saved.png", { root, element: rl });
  await rl.getByLabel("Limit (MB)").fill("5");
  await rl.getByRole("button", { name: "Set limit" }).click();
  await settle(a, 2000);
  await say(a, "ADM-004 back to 5");

  // Weekly slots on Docs FSP Batch 1 (setup for TT-001; tells the batch's students and their counselors)
  await a.goto("/it/admin/timetable");
  await settle(a);
  const batchSel = a.getByLabel("Batch", { exact: true }).first();
  const bv = await batchSel.locator("option", { hasText: "Docs FSP Batch 1" }).getAttribute("value");
  await batchSel.selectOption(bv!);
  await settle(a);
  const add = a.locator("form").filter({ has: a.getByRole("button", { name: "Add slot" }) }).last();
  for (const [day, start, end, topic] of [["Monday", "10:00", "12:00", "Python basics"], ["Wednesday", "10:00", "12:00", "Web with Django"]]) {
    await add.getByLabel("Day", { exact: true }).selectOption({ label: day });
    await add.getByLabel("Starts (IST)").fill(start);
    await add.getByLabel("Ends (IST)").fill(end);
    await add.getByLabel("Mode").selectOption("online");
    await add.getByLabel("Class link (optional)").fill("https://meet.example.test/docs-fsp");
    await add.getByLabel("Topic (optional)").fill(topic);
    await add.getByRole("button", { name: "Add slot" }).click();
    await settle(a, 2000);
    await say(a, `TT-001 slot ${day}`);
  }
  console.log(`VERIFY TT-001 admin slots: ${await text(a.locator("main"))}`);

  // ===== Counselor A =====
  const c = await ctxPage(browser);
  await signIn(c, A, "test", /\/it\/counselor\/dashboard/, "/it/login");
  const S = "students";

  // STU-001 My students
  await c.goto("/it/counselor/students");
  await settle(c);
  console.log(`VERIFY STU-001 list: ${await text(c.locator("main"))}`);
  await shoot(c, S, "01-my-students.png", { root });
  await c.getByLabel("Search records").fill("Arjun");
  await settle(c, 1000);
  await shoot(c, S, "02-my-students-search.png", { root, element: c.locator("main .workspace").first() });

  // STU-002 Student 360
  await c.goto(`/it/counselor/students/${ids.arjun}`);
  await settle(c);
  console.log(`VERIFY STU-002 360: ${await text(c.locator("main"))}`);
  await shoot(c, S, "03-student-360.png", { root, fullPage: true });

  // STU-003 Student record
  await c.goto(`/it/counselor/students/${ids.arjun}/profile`);
  await settle(c);
  const pd = c.locator("main form").filter({ has: c.getByRole("button", { name: "Save details" }) }).first();
  await pd.getByLabel("Date of birth").fill("2001-04-12");
  await pd.getByLabel("City").fill("Hyderabad");
  await pd.getByLabel("Address").fill("Plot 12, Madhapur");
  await pd.getByLabel("Highest qualification").fill("B.Sc Computer Science");
  await pd.getByLabel("Graduation year").fill("2023");
  await pd.getByLabel("Emergency contact name").fill("Docs Parent Rao");
  await pd.getByLabel("Relation").fill("Father");
  await pd.getByLabel("Emergency contact phone").fill("+91 90000 20301");
  await shoot(c, S, "04-student-record-form.png", { root, element: pd });
  await pd.getByRole("button", { name: "Save details" }).click();
  await settle(c, 2500);
  await say(c, "STU-003 saved");
  console.log(`VERIFY STU-003 record: ${await text(c.locator("main"))}`);
  await shoot(c, S, "05-student-record.png", { root, fullPage: true });

  // NOTE-001 Student notes
  await c.goto(`/it/counselor/students/${ids.arjun}/notes`);
  await settle(c);
  await c.getByRole("button", { name: "Save note" }).click();
  await settle(c, 800);
  await say(c, "NOTE-001 empty");
  await c.getByLabel("New note").fill("Prefers weekend doubt-clearing sessions. Asked about internship support after module 3.");
  await shoot(c, S, "06-note-new.png", { root });
  await c.getByRole("button", { name: "Save note" }).click();
  await settle(c, 2000);
  await say(c, "NOTE-001 saved");
  await c.getByLabel("New note").fill("Classes run on Mondays and Wednesdays, 10:00 to 12:00 IST, from 25 Nov. The class link is on your timetable.");
  await c.getByRole("button", { name: "Save note" }).click();
  await settle(c, 2000);
  c.once("dialog", (d) => { console.log(`VERIFY NOTE-001 share dialog: ${d.message()}`); d.accept(); });
  await c.getByRole("button", { name: "Share with student" }).first().click();
  await settle(c, 2000);
  await say(c, "NOTE-001 shared");
  await shoot(c, S, "07-notes-shared.png", { root });
  c.once("dialog", (d) => { console.log(`VERIFY NOTE-001 stop dialog: ${d.message()}`); d.accept(); });
  await c.getByRole("button", { name: "Stop sharing" }).first().click();
  await settle(c, 2000);
  await say(c, "NOTE-001 stopped");
  await shoot(c, S, "08-notes-stopped.png", { root });
  // share it again so the student view (S10) has a shared note
  c.once("dialog", (d) => d.accept());
  await c.getByRole("button", { name: "Share with student" }).first().click();
  await settle(c, 2000);
  console.log(`VERIFY NOTE-001 final: ${await text(c.locator("main"))}`);

  // Scope: Esha moved to Counselor B
  await c.goto(`/it/counselor/students/${ids.esha}`);
  await settle(c);
  console.log(`VERIFY STU-002 other counselor's student: ${await text(c.locator("body"))}`);
  await shoot(c, S, "09-not-your-student.png", { root });

  // TT-001 timetable
  await c.goto("/it/counselor/timetable");
  await settle(c);
  console.log(`VERIFY TT-001 this week: ${await text(c.locator("main"))}`);
  await c.getByRole("button", { name: "Next week" }).click();
  await settle(c);
  console.log(`VERIFY TT-001 next week: ${await text(c.locator("main"))}`);
  await shoot(c, "timetable", "01-timetable.png", { root });

  // NOTIF-001 notifications
  await c.goto("/it/counselor/notifications");
  await settle(c);
  console.log(`VERIFY NOTIF-001: ${await text(c.locator("main"))}`);
  await shoot(c, "notifications", "01-notifications.png", { root });

  // ===== Counselor B sees Esha =====
  const b = await ctxPage(browser);
  await signIn(b, B, "test", /\/it\/counselor\/dashboard/, "/it/login");
  await b.goto("/it/counselor/students");
  await settle(b);
  console.log(`VERIFY ADM-003 B list: ${await text(b.locator("main"))}`);
  await shoot(b, S, "10-counselor-b-students.png", { root });
  await b.goto("/it/counselor/notifications");
  await settle(b);
  console.log(`VERIFY ADM-003 B notifications: ${await text(b.locator("main"))}`);

  // ===== TASK-001: a partner assigns Counselor A a task =====
  const m = await ctxPage(browser);
  await signIn(m, "partner.one@edusphere.local", "seed", /\/management/, "/admin/login");
  await m.goto("/management/tasks/new");
  await settle(m);
  await m.getByLabel("Title").fill("Call back the November Python enquiries");
  const ov = await m.getByLabel("Owner").locator("option", { hasText: "Docs IT Counselor A" }).first().getAttribute("value");
  await m.getByLabel("Owner").selectOption(ov!);
  await m.getByLabel("Deadline").fill(istDate(5));
  await m.getByRole("button", { name: "Save task" }).click();
  await settle(m, 2500);
  await say(m, "TASK-001 created");
  console.log(`VERIFY TASK-001 mgmt url ${m.url()}`);

  await c.goto("/account/management-tasks");
  await settle(c);
  console.log(`VERIFY TASK-001 mine: ${await text(c.locator("main"))}`);
  await shoot(c, "tasks", "01-management-tasks.png", { root });
  const st = c.getByLabel(/Status/).first();
  await st.selectOption("in_progress");
  await c.getByRole("button", { name: "Update status" }).first().click();
  await settle(c, 2000);
  await say(c, "TASK-001 updated");
  await shoot(c, "tasks", "02-management-task-updated.png", { root });
});
