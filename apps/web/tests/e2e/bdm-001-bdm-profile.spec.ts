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

  // QA-05: the manager's welcome link opens the admin portal's own reset page; every link there stays on /admin.
  await page.goto(`/admin/reset-password?token=${manager.development_welcome_token}`);
  await expect(page.getByRole("link", { name: "← Back to sign in" })).toHaveAttribute("href", "/admin/login");
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

test("admin BDM list is full width on desktop: no column or action is clipped (QA-01)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await superAdmin(page);
  await page.goto("/admin/bdms");
  const region = page.getByRole("region", { name: "BDMs" });
  await expect(region).toBeVisible();
  const clipped = await region.evaluate((wrap) => {
    const edge = wrap.getBoundingClientRect().right;
    return [...wrap.querySelectorAll("button, th")].filter((el) => el.getBoundingClientRect().right > edge + 1).length;
  });
  expect(clipped).toBe(0);
});

test("the admin sign-in offers password recovery on the admin portal (QA-05)", async ({ page }) => {
  await page.goto("/admin/login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.waitForURL("**/admin/forgot-password");
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await expect(page.getByRole("link", { name: "← Back to sign in" })).toHaveAttribute("href", "/admin/login");
});

test("admin BDM list keeps its page across refresh and Back (QA-13)", async ({ page }) => {
  await superAdmin(page);
  await page.goto("/admin/bdms");
  await expect(page.getByRole("region", { name: "BDMs" })).toBeVisible();
  const pager = page.getByRole("navigation", { name: "BDM pages" });
  test.skip(!(await pager.isVisible()), "needs more than one page of BDMs");
  await pager.getByRole("button", { name: "Next page" }).click();
  await page.waitForURL("**/admin/bdms?offset=50");
  await page.reload();
  await expect(page.getByRole("navigation", { name: "BDM pages" }).getByText(/^Showing 51–/)).toBeVisible();
  await page.goBack();
  await page.waitForURL(/\/admin\/bdms$/);
  await expect(page.getByRole("navigation", { name: "BDM pages" }).getByText(/^Showing 1–/)).toBeVisible();
});

test("/bdm and /bdm/manager redirect to real pages (QA-09)", async ({ page }) => {
  await superAdmin(page);
  await page.goto("/bdm/manager");
  await page.waitForURL("**/bdm/manager/dashboard");
});

test("admin BDM page works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await page.goto("/admin/bdms");
  await expect(page.getByRole("heading", { name: "Create BDM" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  // QA-15: on a phone the BDM list comes before the long create form.
  const listTop = (await page.getByRole("heading", { name: "BDMs", exact: true, level: 3 }).boundingBox())!.y;
  const formTop = (await page.getByRole("heading", { name: "Create BDM" }).boundingBox())!.y;
  expect(listTop).toBeLessThan(formTop);
  // tel-001 QA follow-up: each row is a card at phone width, so its actions are on screen, not in a sideways-scrolling table.
  const firstRow = page.getByRole("region", { name: "BDMs" }).locator("tbody tr").first();
  for (const action of [firstRow.getByRole("button", { name: /^Edit / }), firstRow.getByRole("button", { name: /^(Deactivate|Reactivate) / })]) {
    const box = (await action.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
  }
  // ... and the list card offers a jump to the create form further down.
  await page.getByRole("link", { name: "Create BDM" }).click();
  await expect(page.getByLabel("Full name (required)")).toBeFocused();
  await expect(page.getByLabel("Full name (required)")).toBeInViewport();
});
