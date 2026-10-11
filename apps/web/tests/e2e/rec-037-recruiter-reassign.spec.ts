import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// rec-037 (DEC-SCOPE-175 RC2/RC3/RC5): the super admin's Deactivate of a recruiter who holds a company is refused with the server's
// sentence; the placement manager opens Team, sees the recruiter's work and reassigns everything to another recruiter; the old recruiter
// can no longer read the company and the Deactivate then succeeds. The Team page fits a phone.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const manager = await post(page, "/api/v1/admin/users", { role: "placement_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `rec037-m-${stamp}@example.local` });
  const recruiter = (suffix: string, name: string) => post(page, "/api/v1/admin/users", {
    role: "placement_team", full_name: `${name} ${stamp}`, email: `rec037-${suffix}-${stamp}@example.local`,
    recruiter_profile: { employee_id: `R37-${stamp}-${suffix}`, reporting_manager_user_id: manager.id },
  });
  const leaving = await recruiter("a", "E2E Leaving");
  const taking = await recruiter("b", "E2E Taking");
  const { company } = await post(page, "/api/v1/recruiter/companies", { name: `E2E Reassign Company ${stamp}`, assigned_recruiter_user_id: leaving.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, leaving, taking]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, leaving, taking, company };
}

async function deactivateAsAdmin(page: Page, employeeId: string, name: string) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  await page.goto("/admin/recruiter-staff");
  await page.getByRole("searchbox", { name: "Search recruiters" }).fill(employeeId);
  await page.getByRole("searchbox", { name: "Search recruiters" }).press("Enter");
  await page.getByRole("button", { name: `Deactivate ${name}` }).click();
}

test("a recruiter's deactivation waits for the manager's reassignment", async ({ page }) => {
  const stamp = Date.now();
  const { manager, leaving, company } = await setUp(page, stamp);
  const leavingName = `E2E Leaving ${stamp}`;
  const takingName = `E2E Taking ${stamp}`;

  await deactivateAsAdmin(page, `R37-${stamp}-a`, leavingName);
  await expect(page.locator(".form-error[role=alert]")).toHaveText(
    "This recruiter has 1 company. A placement manager must reassign them (Team page) before deactivation.");

  await signIn(page, "/admin/login", manager.email);
  await page.goto("/recruiter/manager/team");
  const row = page.getByRole("row", { name: new RegExp(leavingName) });
  await row.getByRole("button", { name: `Reassign ${leavingName}'s work` }).click();
  const group = page.getByRole("group", { name: `Reassign ${leavingName}'s work` });
  await expect(group).toContainText(`${leavingName} has 1 company, 0 requirements and 0 open follow-ups.`);
  const combo = group.getByRole("combobox", { name: /Move everything to/ });
  await combo.fill(takingName);
  await page.getByRole("option", { name: new RegExp(takingName) }).click();
  await group.getByRole("button", { name: "Reassign", exact: true }).click();
  await expect(page.getByRole("row", { name: new RegExp(leavingName) }).getByRole("status")).toHaveText(
    `Moved to ${takingName}: 1 company, 0 requirements and 0 open follow-ups.`);
  await expect(page.getByRole("row", { name: new RegExp(takingName) }).getByRole("cell", { name: "1", exact: true }).first()).toBeVisible();

  await signIn(page, "/it/login", leaving.email);
  expect((await page.request.get(`/api/v1/recruiter/companies/${company.id}`)).status()).toBe(404);

  await deactivateAsAdmin(page, `R37-${stamp}-a`, leavingName);
  await expect(page.getByRole("button", { name: `Reactivate ${leavingName}` })).toBeVisible();
});

test("the Team page fits a phone", async ({ page }) => {
  const stamp = Date.now();
  const { manager } = await setUp(page, stamp);
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "/admin/login", manager.email);
  await page.goto("/recruiter/manager/team");
  await expect(page.getByRole("button", { name: `Reassign E2E Leaving ${stamp}'s work` })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
