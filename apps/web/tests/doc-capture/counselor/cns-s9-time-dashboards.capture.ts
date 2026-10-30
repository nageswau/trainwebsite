import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S9 (docs/counselor-crm/documentation-plan.md): DOC-CNS-FUP-002, FUP-003, ESC-001, ESC-002, DASH-001, SRCH-001, REP-001,
// PERF-001, PERF-002, the CFG-002 Run now step, and the S9 leftovers (OFR-001 expired, OFR-002 met, DOC-003 overdue, CAL-001 no-show,
// TASK-001 "Given by", LEAD-009 milestones, Super Admin † checks). Owner instruction 2026-10-30: the overdue/expired state was prepared
// by moving Day-1 dates 4 days back in the cnsdocs database and running the expiry jobs (see documentation-progress.md).
const root = COUNSELOR_ROOT;
const file = (n: string) => path.join(process.env.DOCS_FILES_DIR!, n);
const IST = 5.5 * 3600_000;
const istDate = (days = 0) => new Date(Date.now() + IST + days * 86_400_000).toISOString().slice(0, 10);
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
async function page(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
async function evalCard(c: Page, student: string) {
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const ev = c.locator(".action-card").filter({ hasText: "Evaluate Applications" }).first();
  return ev.locator(`xpath=.//h4[normalize-space()='${student}']/ancestor::div[contains(concat(' ',@class,' '),' card ')][1]`).first();
}
async function open360(c: Page, search: string) {
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const my = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  await c.fill("#my-students-q", search);
  await my.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await my.getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/students\/[^/?]+/);
  return c.url().split("?")[0];
}

test("Counselor CRM S9 time-based states, dashboards, oversight", async ({ browser }) => {
  test.setTimeout(1_200_000);

  // ===== Overseas Admin: Run reminders now (CFG-002), counselor tasks + escalation (ESC-001/002), performance (PERF-001/002) =====
  const a = await page(browser);
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/overseas/admin/reminder-rules");
  await a.waitForTimeout(2000);
  await a.getByRole("button", { name: "Run reminders now" }).click();
  await a.waitForTimeout(4000);
  await say(a, "CFG-002 run now");
  await toTop(a.getByRole("heading", { name: "Run reminders now" }).first());
  await shoot(a, "config", "11-run-reminders-now.png", { root });
  await a.reload();
  await a.waitForTimeout(2000);
  const recent = a.locator("section, .card").filter({ has: a.getByRole("heading", { name: "Recent reminders" }) }).last();
  console.log(`VERIFY CFG-002 recent: ${await text(recent)}`);
  await shoot(a, "config", "12-recent-reminders.png", { root, element: recent });

  await a.goto("/overseas/admin/dashboard");
  await a.waitForTimeout(2500);
  const dash = await text(a.locator("main"));
  console.log(`VERIFY ESC-002 OA dashboard has escalation notice: ${dash.includes("Overdue work escalated")} :: ${dash.slice(0, 900)}`);
  if (dash.includes("Overdue work escalated")) await shoot(a, "escalation", "05-escalation-notice.png", { root, center: a.getByText("Overdue work escalated").first() });

  await a.goto("/overseas/admin/counselor-tasks");
  await a.waitForTimeout(2500);
  console.log(`VERIFY ESC-001 page: ${await text(a.locator("main"))}`);
  await shoot(a, "escalation", "01-counselor-tasks.png", { root });
  const tf = a.locator("form").filter({ has: a.getByLabel("Title") }).first();
  await tf.getByLabel("Title").fill("Docs Prepare visa file for Docs Walk-in Student");
  await tf.getByLabel("Counselor").selectOption({ label: "Docs Counselor A" }).catch(async () => console.log(`VERIFY ESC-001 counselor options ${JSON.stringify(await tf.getByLabel("Counselor").locator("option").allInnerTexts())}`));
  await tf.getByLabel("Due date").fill(istDate(2));
  await tf.getByLabel("Priority").selectOption({ label: "High" }).catch(() => {});
  await a.waitForTimeout(800);
  const about = await tf.getByLabel(/About/).locator("option").allInnerTexts().catch(() => []);
  const ab = about.find((o) => /Walk-in Student/.test(o));
  if (ab) await tf.getByLabel(/About/).selectOption({ label: ab });
  await shoot(a, "escalation", "02-add-task-for-counselor.png", { root, element: tf });
  await tf.getByRole("button", { name: "Add task" }).click();
  await a.waitForTimeout(2000);
  await say(a, "ESC-001 task added");
  await a.getByLabel("Show").selectOption({ label: "Overdue" }).catch(() => {});
  await a.getByRole("button", { name: "Apply" }).click().catch(() => {});
  await a.waitForTimeout(1800);
  await shoot(a, "escalation", "03-counselor-tasks-overdue.png", { root });
  const od = a.locator("#overdue");
  console.log(`VERIFY ESC-002 overdue: ${await text(od).catch(() => "no #overdue")}`);
  await shoot(a, "escalation", "04-overdue-by-counselor.png", { root, element: od }).catch(() => {});

  await a.goto("/overseas/admin/counselor-performance");
  await a.waitForTimeout(2500);
  console.log(`VERIFY PERF-001: ${await text(a.locator("main"))}`);
  await shoot(a, "performance", "01-team-performance.png", { root });
  await shoot(a, "performance", "02-team-performance-full.png", { root, element: a.locator("main") });
  await a.getByRole("link", { name: "Docs Counselor A" }).first().click();
  await a.waitForURL(/counselor-performance\/[^/]+$/);
  await a.waitForTimeout(2500);
  console.log(`VERIFY PERF-002: ${await text(a.locator("main"))}`);
  await shoot(a, "performance", "03-counselor-report.png", { root, element: a.locator("main") });

  // ===== Counselor A =====
  const c = await page(browser);
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);
  await c.waitForTimeout(3000);
  console.log(`VERIFY DASH-001: ${await text(c.locator("main"))}`);
  await shoot(c, "dashboard", "01-dashboard.png", { root });
  await shoot(c, "dashboard", "02-dashboard-full.png", { root, element: c.locator("main") });
  const fuSec = c.locator("section, .card").filter({ has: c.getByRole("heading", { name: /Follow-ups due/ }) }).last();
  await shoot(c, "dashboard", "03-follow-ups-due-overdue.png", { root, element: fuSec }).catch(() => {});

  // SRCH-001 quick search.
  const qs = c.locator("form").filter({ has: c.getByRole("button", { name: "Search" }) }).first();
  await qs.getByRole("searchbox").or(qs.locator("input")).first().fill("ab");
  await qs.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(800);
  await say(c, "SRCH-001 too short");
  await qs.locator("input").first().fill("Asha");
  await qs.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(2000);
  const qcard = c.locator("section, .card").filter({ has: c.getByRole("heading", { name: "Quick search" }) }).last();
  console.log(`VERIFY SRCH-001 Asha: ${await text(qcard)}`);
  await shoot(c, "dashboard", "04-quick-search-results.png", { root, element: qcard });
  await qs.locator("input").first().fill("zzqx");
  await qs.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await shoot(c, "dashboard", "05-quick-search-nothing.png", { root, element: qcard });
  await qs.locator("input").first().fill("APP-00000");
  await qs.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  console.log(`VERIFY SRCH-001 APP: ${await text(qcard)}`);
  await qcard.getByRole("link").filter({ hasText: /APP-/ }).first().click().catch(() => console.log("VERIFY SRCH-001 no APP link"));
  await c.waitForTimeout(2000);
  console.log(`VERIFY SRCH-001 APP hit opens ${c.url()}`);

  // FUP-002 / FUP-003 / TASK-001 on Tasks.
  await c.goto("/overseas/counselor/tasks");
  await c.waitForTimeout(2500);
  console.log(`VERIFY FUP-002/TASK tasks page: ${await text(c.locator("main"))}`);
  await shoot(c, "tasks", "06-my-tasks-overdue.png", { root, element: c.locator("main") });
  const ovf = c.locator("section, .card").filter({ has: c.getByRole("heading", { name: /Overdue follow-ups/ }) }).last();
  await shoot(c, "follow-ups", "03-overdue-follow-ups.png", { root, element: ovf }).catch(async () => { await toTop(c.getByText(/Overdue follow-ups/).first()); await shoot(c, "follow-ups", "03-overdue-follow-ups.png", { root }); });
  const given = c.locator("li, article, tr").filter({ hasText: "Docs Prepare visa file" }).last();
  await given.getByRole("button", { name: "Edit" }).click().catch(() => {});
  await c.waitForTimeout(800);
  await say(c, "TASK-001 edit admin task");
  await shoot(c, "tasks", "07-task-given-by-admin.png", { root, center: given });

  // OFR-001 expired, OFR-002 condition met (on A2), DOC-003 overdue, OFR-003 result, LEAD-009 milestones.
  let a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Offers" }).click();
  await c.waitForTimeout(1500);
  console.log(`VERIFY OFR-001 expired: ${await text(a1)}`);
  await shoot(c, "offers", "08-offer-expired.png", { root, element: a1 });
  a1 = await evalCard(c, "Docs Lead Asha");
  await a1.getByRole("button", { name: "Interviews" }).click();
  await c.waitForTimeout(1000);
  await a1.getByRole("button", { name: /Edit interview/ }).first().click().catch(() => {});
  await a1.getByLabel("Result").selectOption({ label: "Passed" }).catch(() => {});
  await a1.getByRole("button", { name: "Save interview" }).click().catch(() => {});
  await c.waitForTimeout(1500);
  await say(c, "OFR-003 passed");
  await shoot(c, "offers", "09-interview-passed.png", { root, element: a1 });
  let a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Offers" }).click();
  await c.waitForTimeout(1500);
  await a2.getByRole("button", { name: /Add condition/ }).first().click().catch(() => console.log("VERIFY OFR-002 no Add condition on A2"));
  await c.waitForTimeout(600);
  const cf = a2.locator("form").filter({ hasText: "Owner" }).first();
  await cf.getByLabel("Condition").fill("Submit the CAS acceptance form").catch(() => {});
  await cf.getByLabel("Owner").selectOption({ label: "Student" }).catch(() => {});
  await cf.getByRole("button", { name: "Save condition" }).click().catch(() => {});
  await c.waitForTimeout(1500);
  await say(c, "OFR-002 A2 condition added");
  a2 = await evalCard(c, "Docs Walk-in Student");
  await a2.getByRole("button", { name: "Offers" }).click();
  await c.waitForTimeout(1500);
  await a2.getByRole("button", { name: /Update condition/ }).first().click().catch(() => console.log("VERIFY OFR-002 no Update condition"));
  await c.waitForTimeout(600);
  const uf = a2.locator("form").filter({ hasText: "Status" }).filter({ hasText: "Evidence" }).first();
  console.log(`VERIFY OFR-002 update form: ${await text(uf).catch(() => "none")}`);
  await uf.getByLabel("Status").selectOption({ label: "Met" }).catch(() => {});
  await uf.locator("input[type=file]").setInputFiles(file("docs-evidence.pdf")).catch(() => {});
  await shoot(c, "offers", "10-condition-met-form.png", { root, element: uf }).catch(() => {});
  await uf.getByRole("button", { name: "Save condition" }).click().catch(() => {});
  await c.waitForTimeout(2000);
  await say(c, "OFR-002 met");
  await shoot(c, "offers", "11-condition-met.png", { root, element: a2 });

  const asha = await open360(c, "Asha");
  await c.goto(`${asha}?tab=documents`);
  await c.waitForTimeout(2500);
  const reqCard = c.locator("section[aria-label='Document requests']");
  console.log(`VERIFY DOC-003 overdue: ${await text(reqCard)}`);
  await shoot(c, "documents", "09-request-overdue.png", { root, element: reqCard });

  // LEAD-009 milestones on Asha's lead.
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(2000);
  await c.getByRole("link", { name: "LD-000003" }).click();
  await c.waitForTimeout(2500);
  const ms = c.getByRole("heading", { name: "Student and milestones" }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");
  console.log(`VERIFY LEAD-009 milestones: ${await text(ms)}`);
  await shoot(c, "leads", "24-milestones-with-application.png", { root, element: ms });

  // CAL-001 no-show on CAP-000002.
  await c.goto("/overseas/counselor/appointments");
  await c.waitForTimeout(2500);
  const ns = c.locator("article, li, .card").filter({ hasText: "CAP-000002" }).last();
  await ns.getByRole("button", { name: "Mark no-show" }).click();
  await c.waitForTimeout(800);
  await ns.getByRole("button", { name: /Mark no-show|Save|Confirm/ }).last().click().catch(() => {});
  await c.waitForTimeout(1800);
  await say(c, "CAL-001 no-show");
  await shoot(c, "calendar", "03-appointment-no-show.png", { root, center: c.locator("article, li, .card").filter({ hasText: "CAP-000002" }).last() });

  // REP-001 my performance.
  await c.goto("/overseas/counselor/reports");
  await c.waitForTimeout(2500);
  console.log(`VERIFY REP-001: ${await text(c.locator("main"))}`);
  await shoot(c, "reports", "01-my-performance.png", { root });
  await shoot(c, "reports", "02-my-performance-full.png", { root, element: c.locator("main") });
  await c.getByLabel("Lead division").selectOption({ label: "Overseas" }).catch(() => {});
  await c.getByRole("button", { name: "Show" }).click().catch(() => {});
  await c.waitForTimeout(2000);
  await shoot(c, "reports", "03-my-performance-overseas.png", { root });

  // DASH-001 "View all" target (P6).
  await c.goto("/overseas/counselor/dashboard");
  await c.waitForTimeout(3000);
  const viewAll = c.getByRole("link", { name: /View all/ }).first();
  console.log(`VERIFY DASH-001 view all visible: ${await viewAll.isVisible().catch(() => false)} href=${await viewAll.getAttribute("href").catch(() => "-")}`);

  // ===== Super Admin † checks =====
  const sa = await page(browser);
  await signIn(sa, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  for (const [url, file] of [["/overseas/admin/counselor-tasks", "06-super-admin-counselor-tasks.png"], ["/overseas/admin/counselor-performance", "07-super-admin-performance.png"], ["/overseas/counselor/leads", "08-super-admin-counselor-leads.png"], ["/overseas/counselor/dashboard", "09-super-admin-counselor-dashboard.png"]] as const) {
    await sa.goto(url);
    await sa.waitForTimeout(2500);
    console.log(`VERIFY SA ${url}: ${(await text(sa.locator("main").or(sa.locator("body")).first())).slice(0, 500)}`);
    await shoot(sa, "escalation", file, { root });
  }
});

// Read-only checks (-g "checks"): where a quick-search application hit leads (P7); what the Super Admin sees on counselor Leads (P3).
test("Counselor CRM S9 checks", async ({ browser }) => {
  const c = await page(browser);
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);
  await c.waitForTimeout(2500);
  const qs = c.locator("form").filter({ has: c.getByRole("button", { name: "Search" }) }).first();
  await qs.locator("input").first().fill("APP-000003");
  await qs.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(2000);
  const hits = c.locator("section, .card").filter({ has: c.getByRole("heading", { name: "Quick search" }) }).last();
  const appLink = hits.getByRole("link").filter({ hasText: "Docs Lead Asha" }).last();
  console.log(`VERIFY P7 app link href: ${await appLink.getAttribute("href")}`);
  await appLink.click();
  await c.waitForTimeout(2500);
  console.log(`VERIFY P7 opens ${c.url()} :: ${(await text(c.locator("main"))).slice(0, 300)}`);
  await shoot(c, "dashboard", "06-quick-search-application-opens.png", { root });
  const sa = await page(browser);
  await signIn(sa, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await sa.goto("/overseas/counselor/leads");
  await sa.waitForTimeout(3000);
  const t = await text(sa.locator("main"));
  console.log(`VERIFY P3 SA leads: unable=${t.includes("Unable to load your leads")} :: ${t.slice(t.indexOf("Lead date to"), t.indexOf("Lead date to") + 200)}`);
  await shoot(sa, "escalation", "08-super-admin-counselor-leads.png", { root });
});
