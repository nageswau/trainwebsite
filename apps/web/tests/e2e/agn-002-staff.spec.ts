import { test, expect, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { activateWithToken, E2E_PASSWORD } from "./helpers/welcome";

// AGN-002 -- a Master adds staff; staff work on students without Team/Commissions; deactivate signs them out; reactivate; reset.
// Requires the stack running with `python -m app.seed` applied. The staff-create response never carries the link token (S3), so
// the spec activates the account the way an admin would re-send it (the admin Re-send response carries it in dev/test).

async function signIn(page: Page, email: string, password: string, landing = "/overseas/agent/dashboard") {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function adminActivate(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=agent&provisioning_status=pending_setup")).json();
  const staff = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${staff.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

async function registerApprovedAgency(page: Page, unique: number) {
  const email = `agn002-m-${unique}@example.local`;
  const agency = `Sigma Overseas ${unique}`;
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Sigma Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  await page.locator(".card", { hasText: agency }).getByRole("button", { name: "Approve" }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();
  return email;
}

async function staffPage(browser: Browser) {
  const context = await browser.newContext();
  return context.newPage();
}

test("a Master adds staff who work on students; deactivate, reactivate and reset (AGN-002)", async ({ page, browser }) => {
  test.setTimeout(180_000); // includes the 60 s reset cooldown
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique);
  const staffEmail = `agn002-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  await expect(page.getByText("No staff yet. Add your first staff member below.")).toBeVisible();
  const form = page.getByRole("form", { name: "Add a staff member" });
  await form.getByLabel("Full name").fill("Sigma Staff");
  await form.getByLabel("Email").fill(staffEmail);
  await form.getByRole("button", { name: "Add staff" }).click();
  await expect(page.getByText(/SIG\d*-S001 created/)).toBeVisible();
  await expect(page.getByText("Set-up pending")).toBeVisible();

  const staff = await staffPage(browser);
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await expect(staff.getByRole("link", { name: "Students" }).first()).toBeVisible();
  await expect(staff.getByRole("link", { name: "Team", exact: true })).toHaveCount(0);
  await expect(staff.getByRole("link", { name: "Commissions", exact: true })).toHaveCount(0);
  await staff.goto("/overseas/agent/team");
  await expect(staff.getByText("Only an agency Master can open this page")).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Deactivate Sigma Staff" }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByText(/deactivated\. They have been signed out\./)).toBeVisible();
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  await page.getByRole("button", { name: "Reactivate Sigma Staff" }).click();
  await expect(page.getByText(/reactivated\./)).toBeVisible();
  await signIn(staff, staffEmail, E2E_PASSWORD);

  // The activation link above was issued seconds ago, so the per-account 60 s cooldown (spec E7) refuses the first reset and
  // says so on the row; the confirmation stays open and the reset goes through once the cooldown has passed.
  await page.getByRole("button", { name: "Reset Sigma Staff" }).click();
  await page.getByRole("button", { name: "Confirm reset" }).click();
  await expect(page.getByText(/A link was just sent; wait \d+ seconds before resetting again/)).toBeVisible();
  await page.waitForTimeout(61_000);
  await page.getByRole("button", { name: "Confirm reset" }).click();
  await expect(page.getByText(/set-password link was emailed|login was reset/)).toBeVisible();
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await staff.goto("/overseas/login");
  await staff.fill("#login-email", staffEmail);
  await staff.fill("#login-password", E2E_PASSWORD);
  await staff.click("button:has-text('Sign in securely')");
  await expect(staff).toHaveURL(/\/overseas\/login/);
  await staff.context().close();
});
