import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-032 (DEC-SCOPE-171 RA2/RA3/RA5): the super admin's Deactivate of a manager who is primary on a university is refused with the
// server's sentence; the head opens Team, sees the manager's universities and open tasks, and reassigns everything to another manager;
// the old manager can no longer edit the university and the Deactivate then succeeds. The Team page fits a phone.

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
  const head = await post(page, "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc032-h-${stamp}@example.local` });
  const manager = (suffix: string, name: string) => post(page, "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `${name} ${stamp}`, email: `upc032-${suffix}-${stamp}@example.local`,
    partnership_profile: { employee_id: `U32-${stamp}-${suffix}`, reporting_head_user_id: head.id },
  });
  const leaving = await manager("a", "E2E Leaving");
  const taking = await manager("b", "E2E Taking");
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post(page, "/api/v1/partnership/universities", { name: `E2E Reassign University ${stamp}`, country_id: countries.items[0].id, city: "York" });
  await post(page, `/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: leaving.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, leaving, taking]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, leaving, taking, university };
}

async function deactivateAsAdmin(page: Page, employeeId: string, name: string) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  await page.goto("/admin/partnership-managers");
  await page.getByRole("searchbox", { name: "Search partnership managers" }).fill(employeeId);
  await page.getByRole("searchbox", { name: "Search partnership managers" }).press("Enter");
  await page.getByRole("button", { name: `Deactivate ${name}` }).click();
  await page.getByRole("button", { name: `Confirm deactivate ${name}` }).click();
}

test("a primary manager's deactivation waits for the head's reassignment", async ({ page }) => {
  const stamp = Date.now();
  const { head, leaving, taking, university } = await setUp(page, stamp);
  const leavingName = `E2E Leaving ${stamp}`;
  const takingName = `E2E Taking ${stamp}`;

  await deactivateAsAdmin(page, `U32-${stamp}-a`, leavingName);
  await expect(page.locator(".form-error[role=alert]")).toHaveText(
    "This manager is the primary manager of 1 university. A partnership head must reassign them (Team page) before deactivation.");

  await signIn(page, "/admin/login", head.email);
  await page.goto("/partnership/head/team");
  const row = page.getByRole("row", { name: new RegExp(leavingName) });
  await expect(row.getByRole("cell", { name: "1 primary · 0 backup" })).toBeVisible();
  await row.getByRole("button", { name: `Reassign ${leavingName}'s work` }).click();
  const group = page.getByRole("group", { name: `Reassign ${leavingName}'s work` });
  await expect(group).toContainText(`${leavingName} is primary on 1 university, backup on 0, 0 open tasks.`);
  const combo = group.getByRole("combobox", { name: /Move everything to/ });
  await combo.fill(takingName);
  await page.getByRole("option", { name: new RegExp(takingName) }).click();
  await group.getByRole("button", { name: "Reassign", exact: true }).click();
  await expect(page.getByRole("row", { name: new RegExp(leavingName) }).getByRole("status")).toHaveText(
    `Moved to ${takingName}: primary on 1 university, backup on 0, 0 open tasks.`);
  await expect(page.getByRole("row", { name: new RegExp(takingName) }).getByRole("cell", { name: "1 primary · 0 backup" })).toBeVisible();

  await signIn(page, "/overseas/login", leaving.email);
  const edit = await page.request.patch(`/api/v1/partnership/universities/${university.id}`, { data: { city: "Leeds" } });
  expect(edit.status()).toBe(403);

  await deactivateAsAdmin(page, `U32-${stamp}-a`, leavingName);
  await expect(page.getByRole("button", { name: `Reactivate ${leavingName}` })).toBeVisible();
  expect(taking.id).toBeTruthy();
});

test("the Team page fits a phone", async ({ page }) => {
  const stamp = Date.now();
  const { head } = await setUp(page, stamp);
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "/admin/login", head.email);
  await page.goto("/partnership/head/team");
  await expect(page.getByRole("button", { name: `Reassign E2E Leaving ${stamp}'s work` })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
