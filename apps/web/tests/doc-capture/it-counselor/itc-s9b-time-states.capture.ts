import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S9b (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-FEE-003, STU-004, ADM-011, ADM-014, DASH-001, DASH-002,
// ADM-005, ADM-013, ADM-015, APPT-001 (completed), LEAD-007 (overdue). Runs after itc-s9a, the S9 back-dating SQL and the four jobs
// (`celery call`): every screen here shows a "state prepared by data setup" (owner I2). No payment is recorded (owner I3).
const root = ITC_ROOT;
const A = "docs.itc.a@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2200);
const sec = (p: Page, heading: string | RegExp) =>
  p.getByRole("heading", typeof heading === "string" ? { name: heading, exact: true } : { name: heading }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const ARJUN = "7db2fd54-5ee4-4e79-adcc-8339a1050fee";
const BHAVNA = "343ab86c-8f99-403b-b55a-ca5ce8224e83";

test("IT Counselor CRM S9b time states", async ({ browser }) => {
  test.setTimeout(900_000);
  const leads = JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")).leads as Record<string, string>;

  // ===== Counselor A =====
  const c = await ctxPage(browser);
  await signIn(c, A, "test", /\/it\/counselor\/dashboard/, "/it/login");
  await settle(c, 3000);
  console.log(`VERIFY DASH-001: ${await text(c.locator("main"))}`);
  await shoot(c, "dashboard", "01-dashboard.png", { root });
  await shoot(c, "dashboard", "02-dashboard-full.png", { root, fullPage: true });
  // DASH-002 filters
  const bsel = c.getByLabel("Batch", { exact: true });
  await bsel.selectOption({ label: "Docs FSP Batch 1" });
  await c.getByRole("button", { name: "Apply filters" }).click();
  await settle(c, 3000);
  console.log(`VERIFY DASH-002 url ${c.url()}: ${await text(c.locator("main"))}`);
  await shoot(c, "dashboard", "03-dashboard-filtered.png", { root });
  await c.getByLabel("Status", { exact: true }).selectOption({ label: "Converted" }).catch(() => undefined);
  await c.getByLabel("From", { exact: true }).fill("2026-12-01");
  await c.getByLabel("To", { exact: true }).fill("2026-11-01");
  await c.getByRole("button", { name: "Apply filters" }).click();
  await settle(c, 2500);
  await say(c, "DASH-002 bad dates");
  console.log(`VERIFY DASH-002 bad dates text: ${(await text(c.locator("main"))).slice(0, 600)}`);

  // LEAD-007 overdue follow-up (Arjun)
  await c.goto(`/it/counselor/leads/${leads.arjun}`);
  await settle(c, 2500);
  console.log(`VERIFY LEAD-007 overdue: ${await text(sec(c, /^Follow-ups/))}`);
  await shoot(c, "leads", "40-follow-up-overdue.png", { root, element: sec(c, /^Follow-ups/) });
  console.log(`VERIFY LEAD stage after sweep: ${(await text(c.locator("main"))).slice(0, 500)}`);

  // FEE-003, STU-004 on Arjun's record
  await c.goto(`/it/counselor/students/${ARJUN}/profile`);
  await settle(c, 2500);
  console.log(`VERIFY STU-004 lifecycle: ${await text(sec(c, "Lifecycle"))}`);
  console.log(`VERIFY STU-004 risk: ${await text(sec(c, /^At-risk status/))}`);
  await shoot(c, "students", "11-lifecycle.png", { root, element: sec(c, "Lifecycle") });
  await shoot(c, "students", "12-at-risk-status.png", { root, element: sec(c, /^At-risk status/) });
  console.log(`VERIFY FEE-003 Arjun: ${await text(sec(c, "Fees and reminders"))}`);
  await shoot(c, "fees", "06-fee-overdue.png", { root, element: sec(c, "Fees and reminders") });
  await c.goto(`/it/counselor/students/${BHAVNA}/profile`);
  await settle(c, 2500);
  console.log(`VERIFY FEE-003 Bhavna: ${await text(sec(c, "Fees and reminders"))}`);
  await shoot(c, "fees", "07-fee-reminder-due-soon.png", { root, element: sec(c, "Fees and reminders") });
  await c.goto(`/it/counselor/students/${ARJUN}`);
  await settle(c, 2500);
  console.log(`VERIFY STU-002 360 risk: ${await text(sec(c, "Risk"))}`);

  // Notifications after the jobs
  await c.goto("/it/counselor/notifications");
  await settle(c);
  console.log(`VERIFY NOTIF after jobs: ${await text(c.locator("main"))}`);
  await shoot(c, "notifications", "02-notifications-after-jobs.png", { root });

  // APPT-001: Esha's appointment, now in the past
  await c.goto("/it/counselor/appointments");
  await settle(c, 2500);
  console.log(`VERIFY APPT-001 list: ${await text(c.locator("main"))}`);
  const ap = c.locator("main").getByText("CAP-000001").first().locator("xpath=ancestor::*[.//button[normalize-space()='Mark completed']][1]");
  await shoot(c, "appointments", "02-appointment-past.png", { root, element: ap });
  await ap.getByRole("button", { name: "Mark completed" }).click();
  await settle(c, 800);
  await ap.getByLabel(/Outcome notes/).fill("Discussed the Python Full Stack syllabus and weekend batch options.");
  await shoot(c, "appointments", "03-appointment-complete-form.png", { root, element: ap });
  await ap.getByRole("button", { name: "Mark completed" }).last().click();
  await settle(c, 2500);
  await say(c, "APPT-001 completed");
  console.log(`VERIFY APPT-001 after: ${await text(c.locator("main"))}`);
  await shoot(c, "appointments", "04-appointment-completed.png", { root });

  // ===== IT Admin =====
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  // ADM-011 flagged students
  await a.goto("/it/admin/at-risk");
  await settle(a, 2500);
  console.log(`VERIFY ADM-011 flagged: ${await text(sec(a, "Students at risk"))}`);
  await shoot(a, "admin", "53-students-at-risk.png", { root, element: sec(a, "Students at risk") });
  // ADM-014 escalation notice
  await a.goto("/it/admin/notifications");
  await settle(a, 2500);
  console.log(`VERIFY ADM-014 admin notifications: ${await text(a.locator("main"))}`);
  await shoot(a, "admin", "54-escalation-notification.png", { root });
  // ADM-005 counselor dashboard with Owner
  await a.goto("/it/admin/counselor-dashboard");
  await settle(a, 3000);
  await a.getByLabel("Owner").selectOption({ label: "Docs IT Counselor A" });
  await a.getByRole("button", { name: "Apply filters" }).click();
  await settle(a, 3000);
  console.log(`VERIFY ADM-005 owner A: ${await text(a.locator("main"))}`);
  await shoot(a, "admin", "55-counselor-dashboard-owner.png", { root });
  // ADM-013 status labels: edit Nurture and put it back
  await a.goto("/it/admin/status-labels");
  await settle(a, 2500);
  await shoot(a, "admin", "56-status-labels.png", { root });
  await a.getByRole("button", { name: "Edit Nurture" }).click();
  await settle(a, 800);
  const lf = a.locator("form").filter({ has: a.getByRole("button", { name: "Save Nurture label" }) }).first();
  await lf.getByLabel("Label (required)").fill("Nurture (later)");
  await shoot(a, "admin", "57-status-label-edit.png", { root, element: lf.locator("xpath=ancestor::tr[1]").or(lf).first() });
  await lf.getByRole("button", { name: "Save Nurture label" }).click();
  await settle(a, 2000);
  await say(a, "ADM-013 saved");
  await shoot(a, "admin", "58-status-label-saved.png", { root, element: a.locator("tr", { hasText: "Nurture (later)" }).first() });
  await a.getByRole("button", { name: "Edit Nurture (later)" }).click();
  await settle(a, 800);
  const lf2 = a.locator("form").filter({ has: a.getByRole("button", { name: "Save Nurture label" }) }).first();
  await lf2.getByLabel("Label (required)").fill("Nurture");
  await lf2.getByRole("button", { name: "Save Nurture label" }).click();
  await settle(a, 2000);
  await say(a, "ADM-013 reverted");
  // ADM-015 set a lifecycle stage by hand (Bhavna) and clear it; audit log
  await a.goto(`/it/admin/students/${BHAVNA}/profile`);
  await settle(a, 2500);
  const lc = sec(a, "Lifecycle");
  console.log(`VERIFY ADM-015 card: ${await text(lc)}`);
  const hand = lc.getByRole("form", { name: /Set the stage by hand for/ }).or(lc.locator("form")).first();
  await hand.getByRole("button", { name: "Save stage" }).click().catch(() => undefined);
  await settle(a, 800);
  await say(a, "ADM-015 empty");
  await hand.locator("select").first().selectOption({ label: "Closed" });
  await hand.getByLabel("Reason").fill("Student paused the course for family reasons");
  await shoot(a, "admin", "59-lifecycle-set-by-hand.png", { root, element: lc });
  await hand.getByRole("button", { name: "Save stage" }).click();
  await settle(a, 2500);
  await say(a, "ADM-015 saved");
  await shoot(a, "admin", "60-lifecycle-closed.png", { root, element: sec(a, "Lifecycle") });
  await sec(a, "Lifecycle").getByRole("button", { name: "Clear hand-set stage" }).click();
  await settle(a, 2500);
  await say(a, "ADM-015 cleared");
  const enr = (await lc.getByRole("form", { name: /Set the stage by hand for/ }).first().getAttribute("aria-label").catch(() => null)) ?? "";
  console.log(`VERIFY ADM-015 form label: ${enr}`);
  await a.goto("/it/admin/audit-log?entity_type=enrollment");
  await settle(a, 2500);
  console.log(`VERIFY ADM-015 audit: ${await text(a.locator("main"))}`);
  await shoot(a, "admin", "61-audit-log.png", { root });
});
