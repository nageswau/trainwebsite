import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// rec-001 (AC1, AC3, AC4, AC5): a Super Admin creates a placement manager and a recruiter; each activates from its link and lands on
// its own page; the recruiter edits its mobile; the manager sees it in their team; an existing recruiter shows "No manager" until set.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
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

test("placement manager and recruiter: create, activate, land, edit mobile, team", async ({ page }) => {
  test.setTimeout(45_000);
  const stamp = Date.now();
  await superAdmin(page);
  const managerResponse = await page.request.post("/api/v1/admin/users", {
    data: { role: "placement_manager", division: "global", full_name: `E2E PM ${stamp}`, email: `rec001-m-${stamp}@example.local` },
  });
  expect(managerResponse.status()).toBe(201);
  const manager = await managerResponse.json();
  const recruiterResponse = await page.request.post("/api/v1/admin/users", {
    data: {
      role: "placement_team", full_name: `E2E Recruiter ${stamp}`, email: `rec001-r-${stamp}@example.local`,
      recruiter_profile: { employee_id: `REC-${stamp}`, reporting_manager_user_id: manager.id },
    },
  });
  expect(recruiterResponse.status()).toBe(201);
  const recruiter = await recruiterResponse.json();
  expect(recruiter.division).toBe("it");
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, recruiter.development_welcome_token);
  await signIn(page, "it", recruiter.email, "/recruiter/dashboard");
  await expect(page.getByRole("heading", { name: `Welcome, E2E Recruiter ${stamp}` })).toBeVisible();
  await expect(page.getByText(`REC-${stamp}`)).toBeVisible();
  await page.goto("/recruiter/profile");
  await page.getByLabel("Mobile", { exact: true }).fill("+91 98765 11111");
  await page.getByRole("button", { name: "Save mobile" }).click();
  await expect(page.getByText("Mobile saved.")).toBeVisible();
  await expect(page.locator("dd", { hasText: "+91 98765 11111" })).toBeVisible();
  // A recruiter calling a manager page gets the API's refusal, not the team.
  await page.goto("/recruiter/manager/team");
  await expect(page.getByText("Placement manager role required")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // The manager's welcome link opens the admin portal's own reset page.
  await page.goto(`/admin/reset-password?token=${manager.development_welcome_token}`);
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL("**/admin/login");
  await signIn(page, "admin", manager.email, "/recruiter/manager/team");
  await expect(page.getByRole("region", { name: "Team" }).getByText(`E2E Recruiter ${stamp}`)).toBeVisible();
});

test("signed-out /recruiter visits go to the right sign-in", async ({ page }) => {
  await page.goto("/recruiter/profile");
  await page.waitForURL("**/it/login?next=%2Frecruiter%2Fprofile");
  await page.goto("/recruiter/manager/team");
  await page.waitForURL("**/admin/login?next=%2Frecruiter%2Fmanager%2Fteam");
});

test("Recruiter Staff: a recruiter from the generic form shows No manager until one is set (AC5)", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  await page.request.post("/api/v1/admin/users", {
    data: { role: "placement_manager", division: "global", full_name: `E2E PM2 ${stamp}`, email: `rec001-m2-${stamp}@example.local` },
  });
  const legacy = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "placement_team", division: "it", full_name: `E2E Legacy ${stamp}`, email: `rec001-l-${stamp}@example.local` },
  })).json();
  expect(legacy.recruiter_profile).toEqual({ employee_id: null, reporting_manager: null });
  await page.goto(`/admin/recruiter-staff?q=${encodeURIComponent(`E2E Legacy ${stamp}`)}`);
  const row = page.getByRole("region", { name: "Recruiters" }).locator("tbody tr").first();
  await expect(row.getByText("No manager")).toBeVisible();
  await row.getByRole("button", { name: `Edit E2E Legacy ${stamp}` }).click();
  await page.getByLabel("Employee ID (required)").fill(`LEG-${stamp}`);
  const combo = page.getByRole("combobox", { name: "Reporting manager (required)" });
  await combo.fill(`E2E PM2 ${stamp}`);
  await page.getByRole("option", { name: new RegExp(`E2E PM2 ${stamp}`) }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`Saved E2E Legacy ${stamp}.`)).toBeVisible();
  await expect(row.getByText(`E2E PM2 ${stamp}`)).toBeVisible();
  await expect(row.getByText("No manager")).toHaveCount(0);
});

test("Recruiter Staff works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await page.goto("/admin/recruiter-staff");
  await expect(page.getByRole("heading", { name: "Create recruiter" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Recruiters" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const firstRow = page.getByRole("region", { name: "Recruiters" }).locator("tbody tr").first();
  const box = (await firstRow.getByRole("button", { name: /^Edit / }).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
});
