import { test, expect } from "@playwright/test";

// AGT-004 -- Commission payout request and approval. Builds on the same throwaway-
// student-and-application setup as agt-003-commission-accrual.spec.ts (never reuses the
// shared seeded demo student -- see that spec's own comment for why), advances an
// application to "enrolled" for the seeded demo agent, sets a real amount on the
// resulting estimated commission, claims it as the Agent via the API, then confirms the
// Overseas Admin can approve its payout through the new "Commissions" page action and
// the row reaches "paid".

async function createClaimedCommissionForDemoAgent(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const agents = (await (await page.request.get("/api/v1/overseas-admin/agents")).json()) as { id: string; email: string; approval_status: string }[];
  const agent = agents.find((a) => a.email === "agent@edusphere.local" && a.approval_status === "approved");
  if (!agent) throw new Error("Seeded demo agent not found or not approved");

  const studentName = `E2E Payout Student ${Date.now()}`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email: `agt004-e2e-student-${Date.now()}@example.local`, password: "Sup3r-Secret-Pass!", full_name: studentName, division: "overseas", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();

  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const target = universities[0];

  const created = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: target.id, agent_id: agent.id } });
  expect(created.ok()).toBeTruthy();
  const applicationId = (await created.json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const advanced = await page.request.patch(`/api/v1/workflows/overseas/applications/${applicationId}`, { data: { status: "enrolled" } });
  expect(advanced.ok()).toBeTruthy();

  const rows = (await (await page.request.get("/api/v1/portal/overseas/admin/commissions")).json()).rows as { id: string; student: string }[];
  const commissionRow = rows.find((r) => r.student === studentName);
  if (!commissionRow) throw new Error("Auto-created commission not found for the throwaway student");
  const commissionId = commissionRow.id;

  const amountSet = await page.request.patch(`/api/v1/workflows/overseas/agent/commissions/${commissionId}`, { data: { amount: 20000 } });
  expect(amountSet.ok()).toBeTruthy();

  await page.request.post("/api/v1/auth/login", { data: { email: "agent@edusphere.local", password: "Demo@123", division: "overseas" } });
  const claimed = await page.request.post(`/api/v1/workflows/overseas/agent/commissions/${commissionId}/claim`);
  expect(claimed.ok()).toBeTruthy();

  return { commissionId, studentName };
}

test("Overseas Admin approves a claimed commission's payout and it reaches 'paid' (AGT-004-AC01)", async ({ page }) => {
  const { commissionId, studentName } = await createClaimedCommissionForDemoAgent(page);

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/commissions");
  const searchBox = page.getByLabel("Search records");
  await searchBox.fill(studentName);
  const row = page.locator("table tbody tr", { hasText: studentName });
  await expect(row).toBeVisible();
  await expect(row).toContainText("claimed");

  await page.getByLabel("Commission reference (must be claimed)").fill(commissionId);
  await page.click("button:has-text('Approve commission payout')");
  await expect(page.getByText("Payout approved -- commission marked paid.")).toBeVisible();

  await searchBox.fill(studentName);
  await expect(row).toContainText("paid");
});

test("a non-admin cannot approve a commission payout (AGT-004-AC03)", async ({ page }) => {
  const { commissionId } = await createClaimedCommissionForDemoAgent(page);

  await page.request.post("/api/v1/auth/login", { data: { email: "agent@edusphere.local", password: "Demo@123", division: "overseas" } });
  const response = await page.request.post(`/api/v1/overseas-admin/commissions/${commissionId}/approve-payout`);
  expect(response.status()).toBe(403);
});
