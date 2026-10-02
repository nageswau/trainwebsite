import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-001 (AC01, AC05, AC06, AC12): a Super Admin creates a BDM manager and a College BDM; each activates from its link and lands on
// its own page; the BDM is in the manager's team. Throwaway accounts through the real admin API.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await expect(page.getByRole("heading", { name: "Administration sign-in" })).toBeVisible();
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("manager and College BDM: create, activate, land, team", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const managerResponse = await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm001-m-${stamp}@example.local` },
  });
  expect(managerResponse.status()).toBe(201);
  const manager = await managerResponse.json();
  const bdmResponse = await page.request.post("/api/v1/admin/users", {
    data: {
      role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm001-b-${stamp}@example.local`,
      bdm_profile: { bdm_type: "college", employee_id: `E2E-${stamp}`, territory: "Kochi", reporting_manager_user_id: manager.id },
    },
  });
  expect(bdmResponse.status()).toBe(201);
  const bdm = await bdmResponse.json();
  expect(bdm.division).toBe("it");
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, bdm.development_welcome_token);
  await signIn(page, "it", bdm.email, "/bdm/my-day");
  await expect(page.getByText(`E2E-${stamp}`)).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // The manager's welcome link opens the /it reset page (its URL is unchanged); the form sends them on to /admin/login.
  await page.goto(`/it/reset-password?token=${manager.development_welcome_token}`);
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL("**/admin/login");
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.getByRole("link", { name: "View team" }).click();
  await expect(page.getByRole("region", { name: "Team" }).getByText(`E2E BDM ${stamp}`)).toBeVisible();
});

test("signed-out /bdm visits go to the right sign-in", async ({ page }) => {
  await page.goto("/bdm/my-day");
  await page.waitForURL("**/bdm/sign-in?next=%2Fbdm%2Fmy-day");
  await expect(page.getByRole("link", { name: "College BDM" })).toHaveAttribute("href", "/it/login?next=%2Fbdm%2Fmy-day");
  await page.goto("/bdm/manager/team");
  await page.waitForURL("**/admin/login?next=%2Fbdm%2Fmanager%2Fteam");
});

test("admin BDM page works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await page.goto("/admin/bdms");
  await expect(page.getByRole("heading", { name: "Create BDM" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
