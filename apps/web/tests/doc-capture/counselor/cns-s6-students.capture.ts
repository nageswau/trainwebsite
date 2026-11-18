import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, password, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S6 (docs/counselor-crm/documentation-plan.md): DOC-CNS-STU-001..007, STU-010, HO-003, HO-004, ADM-003, ADM-004.
const root = COUNSELOR_ROOT;
const A = "docs.counselor.a@example.test";
const SELF = { name: "Docs Self-registered Student", email: "docs.self.student@example.com", phone: "+91 90000 10201" };
const WALKIN = { name: "Docs Walk-in Student", email: "docs.walkin.student@example.test", phone: "+91 90000 10202" };
const PENDING = { name: "Docs Pending Walk-in", email: "docs.pending.walkin@example.test", phone: "+91 90000 10203" };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
async function page(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
// Picks an option in a SearchableSelect (combobox) by typing.
async function pick(scope: Locator | Page, type: string, option: RegExp) {
  const box = scope.locator("input[role=combobox]").first();
  await box.fill(type);
  await (scope as Page).waitForTimeout?.(1200);
  const opts = scope.locator("[role=option]");
  await opts.filter({ hasText: option }).first().click();
}

test("Counselor CRM S6 students and the Student 360", async ({ browser }) => {
  test.setTimeout(900_000);

  // ===== HO-004 a student registers on the website =====
  const s = await page(browser);
  await s.goto("/overseas/register");
  await s.waitForTimeout(1500);
  await s.fill("#reg-full-name", SELF.name);
  await s.fill("#reg-email", SELF.email);
  await s.fill("#reg-phone", SELF.phone);
  await s.fill("#reg-password", password("test"));
  await shoot(s, "handoffs", "06-student-self-registration.png", { root });
  await s.getByRole("button", { name: "Create account" }).click();
  await s.waitForURL(/\/overseas\/student\//, { timeout: 30_000 }).catch(async () => say(s, "HO-004 register"));
  await s.waitForTimeout(2000);
  console.log(`VERIFY HO-004 landing ${s.url()} :: ${(await s.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 500)}`);

  // ===== Counselor A: walk-in students (STU-003) =====
  const c = await page(browser);
  await signIn(c, A, "test", /\/overseas\/counselor\/dashboard/);
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const add = c.locator("form[aria-label='Add a walk-in student']");
  await add.locator("#walk-in-full-name").fill(WALKIN.name);
  await add.locator("#walk-in-email").fill(WALKIN.email);
  await add.locator("#walk-in-phone").fill(WALKIN.phone);
  await shoot(c, "students", "06-add-walk-in-student.png", { root, element: add });
  await add.getByRole("button", { name: "Create account" }).click();
  await c.waitForTimeout(2000);
  await say(c, "STU-003 created walk-in");
  await shoot(c, "students", "07-walk-in-student-created.png", { root, element: add });
  await c.reload();
  await c.waitForTimeout(2000);
  await add.locator("#walk-in-full-name").fill(PENDING.name);
  await add.locator("#walk-in-email").fill(PENDING.email);
  await add.getByRole("button", { name: "Create account" }).click();
  await c.waitForTimeout(2000);
  await say(c, "STU-003 created pending");
  await c.reload();
  await c.waitForTimeout(2000);
  await add.locator("#walk-in-full-name").fill("Docs Duplicate Walk-in");
  await add.locator("#walk-in-email").fill(WALKIN.email);
  await add.getByRole("button", { name: "Create account" }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-003 duplicate");
  await shoot(c, "students", "08-walk-in-duplicate-email.png", { root, element: add });

  // STU-002 My students + edit / resend on the pending one.
  await c.reload();
  await c.waitForTimeout(2500);
  const my = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  console.log(`VERIFY STU-002 card: ${await text(my)}`);
  await shoot(c, "students", "03-my-students.png", { root, element: my });
  const prow = my.locator("li, tr, article").filter({ hasText: PENDING.email }).first();
  await prow.getByRole("button", { name: "Edit" }).click();
  await c.waitForTimeout(500);
  await prow.getByLabel(/Phone/).fill(PENDING.phone);
  await shoot(c, "students", "09-edit-pending-walk-in.png", { root, element: prow });
  await prow.getByRole("button", { name: "Save" }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-003 edited");
  const prow2 = my.locator("li, tr, article").filter({ hasText: PENDING.email }).first();
  await prow2.getByRole("button", { name: /Resend link/ }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-003 resend");
  await shoot(c, "students", "10-resend-link.png", { root, element: my });
  await my.locator("li, tr, article").filter({ hasText: PENDING.email }).first().getByRole("button", { name: /Resend link/ }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-003 resend again");
  await c.selectOption("#my-students-source", { label: "Walk-in" });
  await c.waitForTimeout(1500);
  await shoot(c, "students", "04-my-students-source-walk-in.png", { root, element: my });
  await c.selectOption("#my-students-source", { label: "All sources" });
  await c.fill("#my-students-q", "Asha");
  await my.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await shoot(c, "students", "05-my-students-search.png", { root, element: my });

  // STU-004..007 Student 360 for Docs Lead Asha (converted in S4).
  await my.getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/overseas\/counselor\/students\/[^/?]+/);
  await c.waitForTimeout(2500);
  const stuUrl = c.url().split("?")[0];
  console.log(`VERIFY STU-004 overview: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "11-student-360-overview.png", { root });
  await shoot(c, "students", "12-student-360-overview-full.png", { root, fullPage: true });

  // STU-005 profile tabs.
  await c.goto(`${stuUrl}?tab=academic`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY STU-005 academic: ${await text(c.locator("main"))}`);
  await c.getByLabel("Date of birth").fill("2003-04-12").catch(() => console.log("VERIFY no DOB"));
  await c.getByLabel("Nationality").fill("Indian").catch(() => {});
  await c.getByLabel("City").first().fill("Hyderabad").catch(() => {});
  await c.getByRole("button", { name: "Add qualification" }).click().catch(() => {});
  await c.waitForTimeout(400);
  await c.getByLabel("Level").first().selectOption({ label: "Bachelor's degree" }).catch(() => {});
  await c.getByLabel("Qualification", { exact: true }).first().fill("B.Tech Computer Science").catch(() => {});
  await c.getByLabel("Institution").first().fill("Docs Institute of Technology").catch(() => {});
  await c.getByLabel("Year completed").first().fill("2025").catch(() => {});
  await c.getByLabel("Score type").first().selectOption({ label: "Percentage" }).catch(() => {});
  await c.getByLabel("Score", { exact: true }).first().fill("78").catch(() => {});
  await shoot(c, "students", "13-profile-academic.png", { root, fullPage: true });
  await c.getByRole("button", { name: "Save profile" }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-005 academic saved");
  await c.goto(`${stuUrl}?tab=preferences`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY STU-005 preferences: ${await text(c.locator("main"))}`);
  const country = c.getByPlaceholder(/Add a country/);
  for (const name of ["United Kingdom", "Ireland"]) {
    await country.fill(name).catch(() => {});
    await c.waitForTimeout(800);
    await c.getByRole("option", { name: new RegExp(name) }).first().click().catch(async () => country.press("Enter").catch(() => {}));
  }
  await c.getByLabel("Course or subject").fill("MSc Data Science").catch(() => {});
  await c.getByLabel("Study level").selectOption({ label: "Postgraduate" }).catch(() => {});
  await c.getByLabel(/Month/).first().selectOption({ label: "September" }).catch(() => {});
  await c.getByLabel(/Year/).first().selectOption({ label: "2027" }).catch(() => {});
  await c.getByLabel("Study mode").selectOption({ label: "Full-time" }).catch(() => {});
  await c.getByLabel("Budget from").fill("1800000").catch(() => {});
  await c.getByLabel("Budget to").fill("2500000").catch(() => {});
  await c.getByLabel("Budget currency").selectOption({ label: "INR" }).catch(() => {});
  await c.getByRole("button", { name: "Save profile" }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-005 preferences saved");
  await shoot(c, "students", "14-profile-preferences.png", { root, fullPage: true });
  await c.goto(`${stuUrl}?tab=english`);
  await c.waitForTimeout(2000);
  await c.getByRole("button", { name: "Add English test" }).click().catch(() => {});
  await c.waitForTimeout(400);
  await c.getByLabel("Test", { exact: true }).first().selectOption({ label: "IELTS" }).catch(() => {});
  await c.getByLabel("Status").first().selectOption({ label: "Taken" }).catch(() => {});
  await c.getByLabel("Overall score").first().fill("7.0").catch(() => {});
  await c.getByLabel("Test date").first().fill("2026-08-20").catch(() => {});
  await c.getByLabel("Valid until").first().fill("2028-08-20").catch(() => {});
  await c.getByRole("button", { name: "Save profile" }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-005 english saved");
  await shoot(c, "students", "15-profile-english.png", { root, fullPage: true });
  await c.goto(`${stuUrl}/profile`);
  await c.waitForTimeout(2000);
  await shoot(c, "students", "16-profile-page.png", { root });

  // STU-006 notes.
  await c.goto(`${stuUrl}/notes`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY STU-006 notes page: ${await text(c.locator("main"))}`);
  for (const note of ["Asha prefers Manchester; wants a scholarship shortlist.", "Discussed September 2027 intake and IELTS validity."]) {
    await c.getByLabel("New note").fill(note);
    await c.getByRole("button", { name: "Save note" }).click();
    await c.waitForTimeout(1500);
  }
  await say(c, "STU-006 saved");
  await shoot(c, "students", "17-student-notes.png", { root });

  // STU-007 activities and history.
  await c.goto(`${stuUrl}?tab=activities`);
  await c.waitForTimeout(2500);
  console.log(`VERIFY STU-007 activities: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "18-tab-activities.png", { root, fullPage: true });
  await c.goto(`${stuUrl}?tab=history`);
  await c.waitForTimeout(2500);
  console.log(`VERIFY STU-007 history: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "19-tab-history.png", { root });

  // ===== Overseas Admin: assign the agency application (ADM-004, HO-003) and students (ADM-003) =====
  const a = await page(browser);
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/overseas/admin/applications");
  await a.waitForTimeout(2500);
  console.log(`VERIFY ADM-004 list: ${await text(a.locator("main"))}`);
  const arow = a.locator("tr").filter({ hasText: "Ananya" }).first();
  await arow.getByRole("button", { name: /Assign counsellor|Change counsellor/ }).click();
  await a.waitForTimeout(800);
  const aform = a.locator("form[aria-label='Change counsellor'], form[aria-label='Assign counsellor']").first();
  await pick(aform, "Docs Counselor A", /Docs Counselor A/);
  await aform.getByLabel(/Reason/).fill("Ritika is on leave; Docs Counselor A takes the UK caseload.");
  await shoot(a, "admin", "12-change-application-counsellor.png", { root, center: aform });
  await aform.getByRole("button", { name: "Save" }).click();
  await a.waitForTimeout(2000);
  await say(a, "ADM-004 assigned");
  await shoot(a, "admin", "13-application-counsellor-changed.png", { root, center: a.locator("tr").filter({ hasText: "Ananya" }).first() });

  await a.goto("/overseas/admin/users");
  await a.waitForTimeout(2500);
  const urow = (name: string) => a.locator("tr").filter({ hasText: name }).first();
  await a.locator("#table-search").fill("Docs").catch(() => {});
  await a.waitForTimeout(1200);
  await urow(SELF.name).getByRole("button", { name: "Assign counsellor" }).click();
  await a.waitForTimeout(800);
  const f1 = a.locator("form[aria-label='Assign counsellor']").first();
  await pick(f1, "Docs Counselor A", /Docs Counselor A/);
  await shoot(a, "admin", "14-assign-student-counsellor.png", { root, center: f1 });
  await f1.getByRole("button", { name: "Save" }).click();
  await a.waitForTimeout(2000);
  await say(a, "ADM-003 assigned self-registered");
  await urow(WALKIN.name).getByRole("button", { name: "Change counsellor" }).click();
  await a.waitForTimeout(800);
  const f2 = a.locator("form[aria-label='Change counsellor']").first();
  await pick(f2, "Docs Counselor B", /Docs Counselor B/);
  console.log(`VERIFY ADM-003 save disabled without reason: ${await f2.getByRole("button", { name: "Save" }).isDisabled()}`);
  await shoot(a, "admin", "15-change-student-counsellor-needs-reason.png", { root, center: f2 });
  await f2.getByLabel(/Reason/).fill("Balancing caseloads this week.");
  await f2.getByRole("button", { name: "Save" }).click();
  await a.waitForTimeout(2000);
  await say(a, "ADM-003 changed to B");
  await shoot(a, "admin", "16-student-counsellor-changed.png", { root, center: urow(WALKIN.name) });
  await urow(WALKIN.name).getByRole("button", { name: "Change counsellor" }).click();
  await a.waitForTimeout(800);
  const f3 = a.locator("form[aria-label='Change counsellor']").first();
  await pick(f3, "Docs Counselor A", /Docs Counselor A/);
  await f3.getByLabel(/Reason/).fill("Student asked to stay with Docs Counselor A.");
  await f3.getByRole("button", { name: "Save" }).click();
  await a.waitForTimeout(2000);
  await say(a, "ADM-003 changed back to A");

  // Super Admin: no counsellor column (What each role sees).
  const sa = await page(browser);
  await signIn(sa, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await sa.goto("/overseas/admin/users");
  await sa.waitForTimeout(2500);
  const saText = await text(sa.locator("main"));
  console.log(`VERIFY ADM-003 SA users: counsellor column=${saText.includes("EDUSPHERE COUNSELLOR") || saText.includes("EduSphere counsellor")} :: ${saText.slice(0, 600)}`);
  await shoot(sa, "admin", "17-super-admin-users-no-counsellor-column.png", { root });

  // ===== Counselor A again: what changed (STU-010), applications table (STU-001), agency source (HO-003) =====
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  console.log(`VERIFY STU-001 table: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "01-application-tracking.png", { root });
  const myc = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  await toTop(myc, 90);
  await shoot(c, "students", "20-my-students-after-assignment.png", { root, element: myc });
  await c.selectOption("#my-students-source", { label: "Agency" });
  await c.waitForTimeout(1500);
  await shoot(c, "students", "21-my-students-agency.png", { root, element: myc });
  const filters = c.locator("form[aria-label='Filter applications']");
  console.log(`VERIFY STU-001 filters: ${await text(filters).catch(() => "none")}`);
  await shoot(c, "students", "02-application-filters.png", { root, element: filters }).catch(() => {});
  // Walk-in student's 360 history shows both reassignments with reasons.
  await c.selectOption("#my-students-source", { label: "Walk-in" });
  await c.waitForTimeout(1500);
  await myc.locator("li, tr, article").filter({ hasText: WALKIN.email }).first().getByRole("link", { name: "Open" }).click();
  await c.waitForURL(/\/overseas\/counselor\/students\/[^/?]+/);
  await c.goto(`${c.url().split("?")[0]}?tab=history`);
  await c.waitForTimeout(2500);
  console.log(`VERIFY STU-010 history: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "22-history-counselor-reassigned.png", { root });
  // Docs Counselor B no longer sees the walk-in student.
  const b = await page(browser);
  await signIn(b, "docs.counselor.b@example.test", "test", /\/overseas\/counselor\/dashboard/);
  await b.goto("/overseas/counselor/students");
  await b.waitForTimeout(2500);
  const myb = b.locator(".action-card").filter({ has: b.locator("#my-students-source") }).last();
  console.log(`VERIFY STU-010 counselor B: ${await text(myb)}`);
  await shoot(b, "students", "23-counselor-b-after-move-back.png", { root, element: myb });
});

// Read-only re-captures of long 360 tabs as element shots (full-page shots repeat the sticky sidebar). Rerun with -g "360 views".
test("Counselor CRM S6 360 views", async ({ browser }) => {
  test.setTimeout(300_000);
  const c = await page(browser);
  await signIn(c, A, "test", /\/overseas\/counselor\/dashboard/);
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  await c.fill("#my-students-q", "Asha");
  await c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last().getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last().getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/overseas\/counselor\/students\/[^/?]+/);
  const base = c.url().split("?")[0];
  // Remove the empty second qualification row left by the first run, then save.
  await c.goto(`${base}?tab=academic`);
  await c.waitForTimeout(2000);
  const q2 = c.getByText("Qualification 2", { exact: true });
  if (await q2.isVisible().catch(() => false)) {
    await c.getByRole("button", { name: "Remove" }).nth(1).click();
    await c.getByRole("button", { name: "Save profile" }).click();
    await c.waitForTimeout(1500);
    await say(c, "STU-005 removed empty qualification");
  }
  const content = c.locator("main");
  for (const [tab, file] of [["overview", "12-student-360-overview-full.png"], ["academic", "13-profile-academic.png"], ["preferences", "14-profile-preferences.png"], ["english", "15-profile-english.png"], ["activities", "18-tab-activities.png"]] as const) {
    await c.goto(`${base}?tab=${tab}`);
    await c.waitForTimeout(2200);
    await shoot(c, "students", file, { root, element: content });
  }
});
