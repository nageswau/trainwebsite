import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { shoot, signIn, toTop } from "./shoot";

// S8 (docs/documentation-plan.md): DOC-DASH-001/002, DOC-NOTIF-001, DOC-COMM-001, DOC-RPT-001..003, DOC-PERF-001, DOC-ADM-006.
// Runs after s7 + the daily reminder job (run once on the docs stack before this spec).
const staffEmail = (key: string) => JSON.parse(readFileSync(String(process.env.DOCS_STAFF_FILE), "utf8"))[key] as string;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (page: Page) => (await page.locator("main").innerText()).replace(/\s+/g, " ");

test("S8 dashboards, notifications, commissions, reports, performance", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext({ acceptDownloads: true });
  const m = await ctx.newPage();
  m.on("dialog", (d) => d.accept());
  await signIn(m, "agent@edusphere.local");

  // --- DOC-DASH-001 Master dashboard ---
  await expect(m.getByText("Whole agency")).toBeVisible();
  await shoot(m, "dashboard", "01-master-dashboard.png");
  await toTop(m.getByRole("heading", { name: "Commission", exact: true }));
  await shoot(m, "dashboard", "02-master-dashboard-commission.png");
  await toTop(m.getByRole("heading", { name: "Staff performance" }).first());
  await shoot(m, "dashboard", "03-master-dashboard-staff.png");
  console.log(`VERIFY DASH-001: ${(await text(m)).slice(0, 1400)}`);

  // --- DOC-NOTIF-001 notifications (Master) ---
  await m.getByRole("link", { name: /^Notifications/ }).first().click();
  await m.waitForURL("**/overseas/agent/notifications");
  await m.waitForTimeout(800);
  await shoot(m, "notifications", "01-notifications-list.png");
  console.log(`VERIFY NOTIF-001: ${(await text(m)).slice(0, 1500)}`);
  const open = m.getByRole("link", { name: /^Open/ }).first();
  if (await open.count()) {
    await open.click();
    await m.waitForTimeout(1000);
    console.log(`VERIFY NOTIF-001 open went to ${new URL(m.url()).pathname}${new URL(m.url()).search}`);
  }

  // --- DOC-ADM-006 admin sets the commission amount ---
  const actx = await browser.newContext();
  const a = await actx.newPage();
  await signIn(a, "overseasadmin@edusphere.local");
  await a.goto("/overseas/admin/commissions");
  await a.waitForTimeout(1000);
  console.log(`VERIFY ADM-006 table: ${(await text(a)).slice(0, 1200)}`);
  const row = a.locator("tr", { hasText: "Aarav Mehta" }).first();
  const commissionId = (await row.locator("td").first().innerText()).trim();
  console.log(`VERIFY ADM-006 commission id length ${commissionId.length}`);
  await shoot(a, "admin-agencies", "09-commissions-table.png");
  const setForm = a.locator("form").filter({ hasText: "Set/adjust commission amount" }).first();
  await setForm.getByLabel(/^Commission reference/).fill(commissionId);
  await setForm.getByLabel(/^Amount/).fill("120000");
  await setForm.getByLabel(/^Currency/).fill("INR");
  await toTop(setForm);
  await shoot(a, "admin-agencies", "10-commission-set-amount.png");
  await setForm.getByRole("button").last().click();
  await a.waitForTimeout(1200);
  await say(a, "ADM-006 set amount");

  // --- DOC-COMM-001 Master claims ---
  await m.goto("/overseas/agent/commissions");
  await m.waitForTimeout(1000);
  console.log(`VERIFY COMM-001 page: ${(await text(m)).slice(0, 900)}`);
  await shoot(m, "commissions", "01-commissions-table.png");
  const claim = m.locator("form").filter({ hasText: "Claim commission" }).first();
  await claim.getByLabel(/commission reference/i).fill(commissionId);
  await toTop(claim);
  await shoot(m, "commissions", "02-claim-form.png");
  await claim.getByRole("button").last().click();
  await m.waitForTimeout(1200);
  await say(m, "COMM-001 claim");
  await m.reload();
  await shoot(m, "commissions", "03-commission-claimed.png");

  // --- DOC-ADM-006 approve payout ---
  await a.reload();
  const payForm = a.locator("form").filter({ hasText: "Approve commission payout" }).first();
  await payForm.getByLabel(/^Commission reference/).fill(commissionId);
  await toTop(payForm);
  await shoot(a, "admin-agencies", "11-commission-approve-payout.png");
  await payForm.getByRole("button").last().click();
  await a.waitForTimeout(1200);
  await say(a, "ADM-006 approve payout");
  await a.reload();
  await shoot(a, "admin-agencies", "12-commissions-paid.png");
  await actx.close();

  // --- DOC-RPT-001/002/003 reports (Master) ---
  await m.goto("/overseas/agent/reports");
  await m.waitForTimeout(1200);
  console.log(`VERIFY RPT-001 page: ${(await text(m)).slice(0, 700)}`);
  await shoot(m, "reports", "01-reports-students.png");
  const tabs = ["Applications", "Universities", "Countries", "Intakes", "Staff performance", "Enrollments", "Commission"];
  let n = 2;
  for (const t of tabs) {
    const tab = m.getByRole("tablist", { name: "Reports" }).getByRole("tab", { name: t, exact: true });
    await tab.click();
    await m.waitForTimeout(1200);
    await shoot(m, "reports", `${String(n++).padStart(2, "0")}-reports-${t.toLowerCase().replace(/\s+/g, "-")}.png`);
  }
  console.log(`VERIFY RPT-003 commission tab: ${(await text(m)).slice(0, 700)}`);
  await m.getByRole("tablist", { name: "Reports" }).getByRole("tab", { name: "Applications", exact: true }).click();
  await m.waitForTimeout(1000);
  console.log(`VERIFY RPT-001 filters: ${JSON.stringify(await m.locator("main label").allInnerTexts())}`);
  const [download] = await Promise.all([
    m.waitForEvent("download", { timeout: 15_000 }).catch(() => null),
    m.getByRole("button", { name: /Download CSV/ }).first().click(),
  ]);
  console.log(`VERIFY RPT-002 download: ${download ? download.suggestedFilename() : "none"}`);
  await shoot(m, "reports", "10-reports-csv.png");

  // --- DOC-PERF-001 staff performance (Master) ---
  await m.goto("/overseas/agent/performance");
  await m.waitForTimeout(1200);
  await shoot(m, "staff-performance", "01-performance.png");
  console.log(`VERIFY PERF-001: ${(await text(m)).slice(0, 1000)}`);
  await m.getByLabel("From").fill("2026-01-01");
  await m.getByLabel("To").fill("2025-01-01");
  await m.getByRole("button", { name: "Apply" }).click();
  await m.waitForTimeout(600);
  await say(m, "PERF-001 date order");
  await shoot(m, "staff-performance", "03-performance-date-error.png");
  await m.getByLabel("To").fill("2026-12-31");
  await m.getByRole("button", { name: "Apply" }).click();
  await m.waitForTimeout(1000);
  const funnel = m.getByLabel("Show funnel for");
  const opt = await funnel.locator("option", { hasText: "Asha Staff" }).first().getAttribute("value");
  if (opt) await funnel.selectOption(opt);
  await m.waitForTimeout(800);
  await shoot(m, "staff-performance", "02-performance-one-staff.png");
  await ctx.close();

  // --- Staff views: dashboard, notifications, reports (with/without permission), performance refusal ---
  let sctx = await browser.newContext();
  let s = await sctx.newPage();
  await signIn(s, staffEmail("a"), "test");
  await expect(s.getByText("Your assigned students")).toBeVisible();
  await shoot(s, "dashboard", "04-staff-dashboard.png");
  await s.goto("/overseas/agent/notifications");
  await s.waitForTimeout(800);
  await shoot(s, "notifications", "02-staff-notifications.png");
  await s.goto("/overseas/agent/reports");
  await s.waitForTimeout(800);
  console.log(`VERIFY RPT staff without permission: ${(await s.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 200)}`);
  await shoot(s, "reports", "12-reports-staff-refused.png");
  await s.goto("/overseas/agent/performance");
  await s.waitForTimeout(800);
  await shoot(s, "staff-performance", "04-performance-staff-refused.png");
  await sctx.close();
  sctx = await browser.newContext();
  s = await sctx.newPage();
  await signIn(s, staffEmail("c"), "test");
  await s.goto("/overseas/agent/reports");
  await s.waitForTimeout(1200);
  console.log(`VERIFY RPT staff with permission: ${(await text(s)).slice(0, 500)}`);
  await shoot(s, "reports", "11-reports-staff-view.png");
  await sctx.close();
});
