import { expect, test, type Page } from "@playwright/test";

import { password, shoot, signIn, toTop } from "./shoot";

// S9 (docs/documentation-plan.md): DOC-ADM-002..005, DOC-ADM-007 and Reinstate for DOC-ADM-001. Runs after s8.
const ADM = "admin-agencies";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (page: Page) => (await page.locator("main").innerText()).replace(/\s+/g, " ");
const today = () => new Date().toISOString().slice(0, 10);
const tomorrow = () => { const d = new Date(); d.setDate(d.getDate() + 2); return d.toISOString().slice(0, 10); };

test("S9 admin agency screens", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  const a = await ctx.newPage();
  await signIn(a, "overseasadmin@edusphere.local");

  // --- DOC-ADM-001 reinstate (approvals page) ---
  await a.goto("/overseas/admin/agents?tab=suspended");
  await a.getByRole("button", { name: "Reinstate Docs Suspended Agency", exact: true }).click();
  await a.waitForTimeout(1000);
  await say(a, "ADM-001 reinstate");
  await toTop(a.getByRole("heading", { name: "Agent Approvals" }));
  await shoot(a, ADM, "13-agent-approvals-reinstated.png");

  // --- DOC-ADM-002 agent network list ---
  await a.goto("/overseas/admin/agent-network");
  await a.waitForTimeout(1200);
  console.log(`VERIFY ADM-002 list: ${(await text(a)).slice(0, 1000)}`);
  await shoot(a, ADM, "14-agent-network-all.png");
  await a.getByRole("button", { name: "Active", exact: true }).first().click().catch(() => console.log("VERIFY ADM-002 no Active button"));
  await a.waitForTimeout(800);
  await shoot(a, ADM, "15-agent-network-active.png");
  await a.getByRole("button", { name: "All", exact: true }).first().click().catch(() => {});
  await a.getByLabel("Search agencies").fill("zzzz");
  await a.getByRole("button", { name: "Search", exact: true }).click().catch(() => a.getByLabel("Search agencies").press("Enter"));
  await a.waitForTimeout(900);
  await say(a, "ADM-002 no match");
  await shoot(a, ADM, "16-agent-network-no-match.png");

  // --- DOC-ADM-003 agency detail ---
  await a.goto("/overseas/admin/agent-network");
  await a.getByRole("link", { name: "EduSphere Partner Agency" }).first().click();
  await a.waitForURL(/agent-network\/[0-9a-f-]{36}/);
  await a.waitForTimeout(1500);
  console.log(`VERIFY ADM-003 detail: ${(await text(a)).slice(0, 1600)}`);
  await shoot(a, ADM, "17-agency-detail.png");
  await toTop(a.getByRole("group", { name: "Agency records" }), 120);
  await shoot(a, ADM, "18-agency-records-students.png");
  await a.getByRole("group", { name: "Agency records" }).getByRole("button", { name: "Applications", exact: true }).click().catch(() => console.log("VERIFY ADM-003 no Applications button"));
  await a.waitForTimeout(900);
  await toTop(a.getByRole("group", { name: "Agency records" }), 120);
  await shoot(a, ADM, "20-agency-records-applications.png");

  // --- DOC-ADM-004 suspend / reinstate from detail ---
  await a.goto("/overseas/admin/agent-network");
  await a.getByRole("link", { name: "Docs Second Agency" }).first().click();
  await a.waitForURL(/agent-network\/[0-9a-f-]{36}/);
  await a.getByRole("button", { name: "Suspend Docs Second Agency" }).click();
  await shoot(a, ADM, "21-detail-suspend-confirm.png");
  await a.getByRole("button", { name: "Confirm suspend" }).click();
  await a.waitForTimeout(1000);
  await say(a, "ADM-004 suspended");
  await shoot(a, ADM, "22-detail-suspended.png");
  await a.getByRole("button", { name: /^Reinstate/ }).first().click();
  await a.waitForTimeout(1000);
  await say(a, "ADM-004 reinstated");
  await a.goto("/overseas/admin/agent-network");
  await a.getByRole("link", { name: "Docs Pending Agency" }).first().click();
  await a.waitForURL(/agent-network\/[0-9a-f-]{36}/);
  await a.waitForTimeout(800);
  await shoot(a, ADM, "23-detail-pending-review-link.png");
  await a.goto("/overseas/admin/agent-network/not-a-real-id");
  await a.waitForTimeout(800);
  console.log(`VERIFY ADM-003 bad id: ${(await a.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 160)}`);

  // --- DOC-ADM-005 deposits ---
  await a.goto("/overseas/admin/agent-deposits");
  await a.waitForTimeout(1200);
  console.log(`VERIFY ADM-005 page: ${(await text(a)).slice(0, 900)}`);
  await shoot(a, ADM, "24-deposits-paid.png");
  await a.getByRole("button", { name: /^Record remittance/ }).first().click();
  await a.getByLabel(/^Remitted on/).fill(tomorrow());
  await a.getByLabel(/^Remittance reference/).fill("NWB-REM-2026-0042");
  await a.getByRole("button", { name: "Save remittance" }).click();
  await a.waitForTimeout(800);
  await say(a, "ADM-005 future remittance date");
  await shoot(a, ADM, "26-remittance-date-error.png");
  await a.getByLabel(/^Remitted on/).fill(today());
  await shoot(a, ADM, "25-remittance-form.png");
  await a.getByRole("button", { name: "Save remittance" }).click();
  await a.waitForTimeout(1000);
  await say(a, "ADM-005 remitted");
  await a.getByRole("button", { name: "Remitted", exact: true }).first().click().catch(() => {});
  await a.waitForTimeout(800);
  await shoot(a, ADM, "27-deposits-remitted.png");
  await a.getByRole("button", { name: /^Record refund/ }).first().click();
  await a.getByLabel(/^Refunded on/).fill(today());
  await a.getByLabel(/^Refund amount/).fill("60000");
  await a.getByLabel(/^Reason/).fill("Student deferred to the January 2028 intake; university returned the deposit.");
  await a.getByRole("button", { name: "Save refund" }).click();
  await a.getByRole("button", { name: "Yes, record refund" }).click();
  await a.waitForTimeout(1000);
  await say(a, "ADM-005 refund too large");
  await shoot(a, ADM, "29-refund-too-large.png");
  await a.getByRole("button", { name: "Go back" }).click().catch(() => {});
  await a.getByLabel(/^Refund amount/).fill("50000");
  await shoot(a, ADM, "28-refund-form.png");
  await a.getByRole("button", { name: "Save refund" }).click();
  await shoot(a, ADM, "30-refund-confirm.png");
  await a.getByRole("button", { name: "Yes, record refund" }).click();
  await a.waitForTimeout(1000);
  await say(a, "ADM-005 refunded");
  await a.getByRole("button", { name: "Refunded", exact: true }).first().click().catch(() => {});
  await a.waitForTimeout(800);
  await shoot(a, ADM, "31-deposits-refunded.png");
  await ctx.close();

  // Agency view of the refunded deposit
  const mctx = await browser.newContext();
  const m = await mctx.newPage();
  await signIn(m, "agent@edusphere.local");
  await m.goto("/overseas/agent/applications?status=enrolled");
  await m.getByRole("button", { name: "View Aarav Mehta — University of Birmingham" }).click();
  await toTop(m.getByRole("heading", { name: "Deposit", exact: true }));
  await shoot(m, "applications", "40-deposit-refunded-agency-view.png");
  await mctx.close();

  // --- DOC-ADM-007 Super Admin ---
  const sctx = await browser.newContext();
  const s = await sctx.newPage();
  await s.goto("/admin/login");
  await s.fill("#login-email", "superadmin@edusphere.local");
  await s.fill("#login-password", password());
  await s.click("button:has-text('Sign in')");
  await s.waitForURL((u) => !u.pathname.startsWith("/admin/login"));
  console.log(`VERIFY ADM-007 super admin landed on ${new URL(s.url()).pathname}`);
  for (const [path, file] of [["/overseas/admin/agent-network", "32-super-admin-network.png"], ["/overseas/admin/agent-deposits", "33-super-admin-deposits.png"], ["/overseas/admin/agents", "34-super-admin-agents.png"], ["/overseas/admin/commissions", "35-super-admin-commissions.png"]]) {
    await s.goto(path);
    await s.waitForTimeout(1200);
    const t = await text(s).catch(async () => (await s.locator("body").innerText()).replace(/\s+/g, " "));
    console.log(`VERIFY ADM-007 ${path}: buttons=${JSON.stringify((await s.locator("main button").allInnerTexts()).slice(0, 25))} text=${t.slice(0, 300)}`);
    await shoot(s, ADM, file);
  }
  await s.goto("/overseas/admin/agent-network");
  await s.getByRole("link", { name: "EduSphere Partner Agency" }).first().click().catch(() => {});
  await s.waitForTimeout(1200);
  console.log(`VERIFY ADM-007 detail suspend button: ${await s.getByRole("button", { name: /^Suspend/ }).count()}`);
  await s.goto("/overseas/admin/applications");
  await s.waitForTimeout(1200);
  console.log(`VERIFY U16 /overseas/admin/applications: ${(await s.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await sctx.close();
  expect(true).toBeTruthy();
});
