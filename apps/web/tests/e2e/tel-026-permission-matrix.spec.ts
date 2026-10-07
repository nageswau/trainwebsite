import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-026 (EVID-019 §22, RBAC_MATRIX §2.41): nav visibility. A telecaller's sidebar holds only their own pages, and every manager page
// (reports, targets, performance) answers with the access card, not data. A manager sees the manager sidebar and is refused the
// telecaller's own dashboard; an IT counselor is refused the telecaller workspace.

const MANAGER_ONLY = ["/telecaller/manager/reports", "/telecaller/manager/targets", "/telecaller/manager/performance", "/telecaller/manager/team"];

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const create = async (data: Record<string, unknown>) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await create({ role: "telecaller_manager", division: "global", full_name: `E2E Matrix Manager ${stamp}`, email: `tel026-m-${stamp}@example.local` });
  const caller = await create({
    role: "telecaller", full_name: `E2E Matrix Telecaller ${stamp}`, email: `tel026-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `PM-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselor = await create({ role: "counselor", division: "it", full_name: `E2E Matrix Counselor ${stamp}`, email: `tel026-c-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, caller, counselor]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, caller, counselor };
}

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const sidebarLinks = (page: Page) => page.getByRole("navigation").first().getByRole("link");

test("§22 nav visibility: each telecaller-CRM role sees only its own pages", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const { manager, caller, counselor } = await setup(page, stamp);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/status of 403/.test(m.text())) errors.push(m.text()); });

  // Telecaller: lands on the dashboard; the sidebar is the telecaller nav, with no manager page in it.
  await signIn(page, "it", caller.email);
  await expect(page).toHaveURL(/\/telecaller\/dashboard$/);
  const nav = sidebarLinks(page);
  await expect(nav.filter({ hasText: "My Leads" })).toHaveCount(1);
  for (const label of ["Reports", "Targets", "Performance", "Lead assignment", "Distribution rules"]) {
    await expect(nav.filter({ hasText: new RegExp(`^${label}$`) })).toHaveCount(0);
  }
  for (const path of MANAGER_ONLY) {
    await page.goto(path);
    await expect(page.getByText(/manager role required/i).first(), path).toBeVisible();
    await expect(page.getByRole("table")).toHaveCount(0);
  }

  // Manager: the manager sidebar; the telecaller's own dashboard refuses them.
  await signIn(page, "admin", manager.email);
  await expect(page).toHaveURL(/\/telecaller\/manager\/team$/);
  for (const label of ["Reports", "Targets", "Performance"]) await expect(sidebarLinks(page).filter({ hasText: new RegExp(`^${label}$`) })).toHaveCount(1);
  await page.goto("/telecaller/dashboard");
  await expect(page.getByText(/Telecaller role required/i).first()).toBeVisible();

  // IT counselor: no telecaller workspace.
  await signIn(page, "it", counselor.email);
  await page.goto("/telecaller/leads");
  await expect(page.getByText(/role required/i).first()).toBeVisible();

  expect(errors).toEqual([]);
});
