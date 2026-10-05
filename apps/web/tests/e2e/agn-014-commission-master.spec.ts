import { test, expect } from "@playwright/test";

import { E2E_PASSWORD } from "./helpers/welcome";
import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-014 -- a Master sees Revenue and the commission report (filter + CSV); staff are refused commissions and see no Revenue.
// Requires the stack running with `python -m app.seed` applied. The commission is made `paid` through the real API: a student
// applies through the new agency's Master, the Overseas Admin enrols it (auto commission) and sets the amount, the Master claims,
// and the admin approves the payout (a system-triggered commission, so the same admin may approve it -- AGT-004 unchanged).

const ADMIN = { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" };
const MASTER_PASSWORD = "Sup3r-Secret-Pass!";

test("a Master sees Revenue and the commission report; staff are refused (AGN-014)", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn014");
  const api = page.request;

  await api.post("/api/v1/auth/login", { data: ADMIN });
  const agents = (await (await api.get("/api/v1/overseas-admin/agents")).json()) as { id: string; email: string }[];
  const master = agents.find((a) => a.email === masterEmail);
  if (!master) throw new Error("the new agency's Master is not listed");

  const studentName = `AGN014 Student ${unique}`;
  const registered = await api.post("/api/v1/auth/register", {
    data: { email: `agn014-st-${unique}@example.local`, password: MASTER_PASSWORD, full_name: studentName, division: "overseas", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  const universities = (await (await api.get("/api/v1/public/universities")).json()) as { id: string }[];
  const created = await api.post("/api/v1/workflows/overseas/applications", { data: { university_id: universities[0].id, agent_id: master.id } });
  expect(created.ok()).toBeTruthy();
  const applicationId = (await created.json()).id as string;

  await api.post("/api/v1/auth/login", { data: ADMIN });
  expect((await api.patch(`/api/v1/workflows/overseas/applications/${applicationId}`, { data: { status: "enrolled" } })).ok()).toBeTruthy();
  const rows = (await (await api.get("/api/v1/portal/overseas/admin/commissions")).json()).rows as { id: string; student: string }[];
  const commissionId = rows.find((r) => r.student === studentName)?.id;
  if (!commissionId) throw new Error("the auto-created commission was not found");
  expect((await api.patch(`/api/v1/workflows/overseas/agent/commissions/${commissionId}`, { data: { amount: 20000 } })).ok()).toBeTruthy();

  await api.post("/api/v1/auth/login", { data: { email: masterEmail, password: MASTER_PASSWORD, division: "overseas" } });
  expect((await api.post(`/api/v1/workflows/overseas/agent/commissions/${commissionId}/claim`)).ok()).toBeTruthy();
  await api.post("/api/v1/auth/login", { data: ADMIN });
  expect((await api.post(`/api/v1/overseas-admin/commissions/${commissionId}/approve-payout`)).ok()).toBeTruthy();

  // Master: Revenue on the dashboard, then the report with a filter, then the CSV of the applied range.
  await signIn(page, masterEmail, MASTER_PASSWORD);
  await expect(page.getByText("Revenue", { exact: true })).toBeVisible();
  await expect(page.getByText("INR 20,000", { exact: true })).toBeVisible();
  await page.goto("/overseas/agent/reports?report=commission"); // AGN-020: the commission report is the Reports page's Commission tab
  await expect(page.getByRole("heading", { name: "Commission report" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "By status" })).toBeVisible();
  const today = new Date().toISOString().slice(0, 10); // UTC day, the report's date basis
  await page.getByLabel("From").fill(today);
  await page.getByLabel("To").fill(today);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("heading", { name: "By status" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe(`agency-commissions-${today}-to-${today}.csv`);

  // Staff: no Commissions link, the server's 403 card on a typed URL, and no Revenue on their dashboard.
  const staffEmail = `agn014-s-${unique}@example.local`;
  await api.post("/api/v1/auth/login", { data: { email: masterEmail, password: MASTER_PASSWORD, division: "overseas" } });
  expect((await api.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "AGN014 Staff", email: staffEmail } })).ok()).toBeTruthy();
  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await expect(staff.getByRole("link", { name: "Commissions", exact: true })).toHaveCount(0);
  await expect(staff.getByText("Revenue", { exact: true })).toHaveCount(0);
  await staff.goto("/overseas/agent/commissions");
  await expect(staff.getByText("Only an agency Master can open this page")).toBeVisible();
});
