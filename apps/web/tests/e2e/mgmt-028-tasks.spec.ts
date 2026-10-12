import { expect, test, type Page } from "@playwright/test";

import { createAndActivate, E2E_PASSWORD } from "./helpers/welcome";

// mgmt-028 (EVID-017 §28, spec MT1-MT14): a partner adds "Approve marketing budget" due today for a staff member; that member opens
// Management tasks from their own sidebar, finds it under Due Today and completes it, and it moves to Completed (AC2). Another staff
// member never sees it (AC3). The staff users are created through the admin API so the test owns every row it checks.

const PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("signed out, /management/tasks sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/tasks");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Ftasks$/);
});

test("a partner assigns a task; its owner completes it from Management tasks; nobody else sees it", async ({ browser }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const title = `Approve marketing budget e2e-${stamp}`;

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, "superadmin@edusphere.local");
  const owner = await createAndActivate(admin.request, "/api/v1/admin/users", {
    role: "partnership_head", division: "global", full_name: `Task Owner ${stamp}`, email: `mgmt028-${stamp}@example.local`,
  });
  const other = await createAndActivate(admin.request, "/api/v1/admin/users", {
    role: "partnership_head", division: "global", full_name: `Other Staff ${stamp}`, email: `mgmt028-other-${stamp}@example.local`,
  });

  const partner = await (await browser.newContext()).newPage();
  await signIn(partner, "partner.one@edusphere.local");
  await partner.goto("/management");
  await partner.getByRole("link", { name: "To-do" }).first().click();
  await expect(partner.getByRole("heading", { level: 2, name: "Management to-do" })).toBeVisible();
  await partner.getByRole("link", { name: "New task" }).click();
  await partner.getByLabel("Title").fill(title);
  await partner.getByLabel("Owner").selectOption({ label: `Task Owner ${stamp} (Partnership Head)` });
  await partner.getByLabel("Priority").selectOption("high");
  await partner.getByRole("button", { name: "Save task" }).click();
  await expect(partner).toHaveURL(/\/management\/tasks\?view=everyone$/);
  await expect(partner.getByRole("region", { name: /^Due Today/ }).getByText(title)).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await signIn(staff, owner.email, E2E_PASSWORD);
  await staff.getByRole("link", { name: "Management tasks" }).first().click();
  await expect(staff).toHaveURL(/\/account\/management-tasks$/);
  const dueToday = staff.getByRole("region", { name: /^Due Today/ });
  await expect(dueToday.getByText(new RegExp(`^${title} — .+ — High priority$`))).toBeVisible();
  await staff.getByLabel(`Status of “${title}”`).selectOption("completed");
  await staff.getByRole("button", { name: "Update status" }).click();
  await expect(staff.getByText("Status updated.")).toBeVisible();
  await expect(staff.getByRole("region", { name: /^Completed/ }).getByText(new RegExp(`^${title}`))).toBeVisible();
  await expect(staff.getByRole("region", { name: /^Due Today/ })).toHaveCount(0);
  await staff.goto("/management/tasks");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  const stranger = await (await browser.newContext()).newPage();
  await signIn(stranger, other.email, E2E_PASSWORD);
  await stranger.goto("/account/management-tasks");
  await expect(stranger.getByText("No management tasks are assigned to you.")).toBeVisible();
  await expect(stranger.getByText(title)).toHaveCount(0);
});
