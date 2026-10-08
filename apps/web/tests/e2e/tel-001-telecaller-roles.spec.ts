import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-001 (AC1, AC3, AC4, AC5): a Super Admin creates a telecaller manager and an IT telecaller; each activates from its link and
// lands on its own page; the telecaller edits its mobile; the manager sees it in their team. Throwaway accounts via the real admin API.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await expect(page.getByText("For Super Admins, BDM Managers, Telecaller Managers and Partnership Heads.")).toBeVisible();
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

test("manager and IT telecaller: create, activate, land, edit mobile, team", async ({ page }) => {
  test.setTimeout(45_000); // a long multi-sign-in journey; the 15s default is tight when the suite runs in parallel
  const stamp = Date.now();
  await superAdmin(page);
  const managerResponse = await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E TL Manager ${stamp}`, email: `tel001-m-${stamp}@example.local` },
  });
  expect(managerResponse.status()).toBe(201);
  const manager = await managerResponse.json();
  const callerResponse = await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Telecaller ${stamp}`, email: `tel001-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `TEL-${stamp}`, reporting_manager_user_id: manager.id },
    },
  });
  expect(callerResponse.status()).toBe(201);
  const caller = await callerResponse.json();
  expect(caller.division).toBe("it");
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, caller.development_welcome_token);
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await expect(page.getByText(`TEL-${stamp}`)).toBeVisible();
  await page.goto("/telecaller/profile");
  await page.getByLabel("Mobile", { exact: true }).fill("+91 98765 00000");
  await page.getByRole("button", { name: "Save mobile" }).click();
  await expect(page.getByText("Mobile saved.")).toBeVisible();
  await expect(page.locator("dd", { hasText: "+91 98765 00000" })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // The manager's welcome link opens the admin portal's own reset page (spec §5.6).
  await page.goto(`/admin/reset-password?token=${manager.development_welcome_token}`);
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL("**/admin/login");
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await expect(page.getByRole("region", { name: "Team" }).getByText(`E2E Telecaller ${stamp}`)).toBeVisible();
});

test("signed-out /telecaller visits go to the right sign-in (AC5)", async ({ page }) => {
  await page.goto("/telecaller/profile");
  await page.waitForURL("**/telecaller/sign-in?next=%2Ftelecaller%2Fprofile");
  await expect(page.getByRole("link", { name: "IT team" })).toHaveAttribute("href", "/it/login?next=%2Ftelecaller%2Fprofile");
  await page.goto("/telecaller/manager/team");
  await page.waitForURL("**/admin/login?next=%2Ftelecaller%2Fmanager%2Fteam");
});

test("a telecaller at the wrong portal gets the correct-portal message (AC3)", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E TL M2 ${stamp}`, email: `tel001-m2-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller", full_name: `E2E TL O ${stamp}`, email: `tel001-o-${stamp}@example.local`,
      telecaller_profile: { team: "overseas", employee_id: `TELO-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await page.goto("/it/login");
  await page.fill("#login-email", caller.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await expect(page.getByText(/sign in at \/overseas\/login/)).toBeVisible();
});

test("admin Telecallers page works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await page.goto("/admin/telecallers");
  await expect(page.getByRole("heading", { name: "Create telecaller" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const listTop = (await page.getByRole("heading", { name: "Telecallers", exact: true, level: 3 }).boundingBox())!.y;
  const formTop = (await page.getByRole("heading", { name: "Create telecaller" }).boundingBox())!.y;
  expect(listTop).toBeLessThan(formTop);
  // QA-04: each row is a card at phone width, so its status and actions are on screen, not in a sideways-scrolling table.
  const firstRow = page.getByRole("region", { name: "Telecallers" }).locator("tbody tr").first();
  for (const action of [firstRow.getByRole("button", { name: /^Edit / }), firstRow.getByRole("button", { name: /^(Deactivate|Reactivate) / })]) {
    const box = (await action.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
  }
  // ... and the list card offers a jump to the create form further down.
  await page.getByRole("link", { name: "Create telecaller" }).click();
  await expect(page.getByLabel("Full name (required)")).toBeFocused();
  await expect(page.getByLabel("Full name (required)")).toBeInViewport();
});
