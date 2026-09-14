import { test, expect } from "@playwright/test";

// AGT-003 -- Commission accrual (automatic trigger). Creates its own throwaway student
// and application (assigned to the seeded demo agent) via the real API, advances it to
// "enrolled" as the seeded Overseas Admin, then confirms the system-triggered
// "estimated" commission appears on the new Overseas Admin "Commissions" page and can
// be set to a real amount there. Deliberately registers a fresh throwaway student rather
// than reusing the seeded demo student -- the demo student's own application list is a
// shared record `agt-002-referrals.spec.ts` asserts a specific status on, and creating
// an application against a real university for that shared student would collide with
// it (same "create your own record, never mutate a shared seeded one" principle used
// throughout this project, see ovs-003-eligibility.spec.ts -- caught by that exact
// collision the first time this spec was written).

async function createEnrolledApplicationForDemoAgent(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const agents = (await (await page.request.get("/api/v1/overseas-admin/agents")).json()) as { id: string; email: string; approval_status: string }[];
  const agent = agents.find((a) => a.email === "agent@edusphere.local" && a.approval_status === "approved");
  if (!agent) throw new Error("Seeded demo agent not found or not approved");

  const studentName = `E2E Commission Student ${Date.now()}`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email: `agt003-e2e-student-${Date.now()}@example.local`, password: "Sup3r-Secret-Pass!", full_name: studentName, division: "overseas", account_type: "student" },
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
  return { applicationId, studentName };
}

test("an application reaching 'enrolled' auto-creates an estimated commission the Overseas Admin can set an amount on (AGT-003-AC01/AC02)", async ({ page }) => {
  const { studentName } = await createEnrolledApplicationForDemoAgent(page);

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
  await expect(row).toContainText("estimated");
  await expect(row).toContainText("system_trigger");

  const commissionId = (await row.locator("td").first().innerText()).trim();
  await page.getByLabel("Commission reference", { exact: true }).fill(commissionId);
  await page.getByLabel("Amount").fill("18000");
  await page.click("button:has-text('Set/adjust commission amount')");
  await expect(page.getByText("Commission amount updated.")).toBeVisible();

  await searchBox.fill(studentName);
  await expect(row).toContainText("eligible");
  await expect(row).toContainText("18,000");
});

test("the commissions workspace requires authentication", async ({ page }) => {
  await page.goto("/overseas/admin/commissions");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
