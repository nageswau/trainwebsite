import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-008 (AC1, AC3, AC4, AC9): a College BDM adds a follow-up for an organization (due today) and a general task (due tomorrow); the
// counts match the list; Done offers the next steps; Cancel keeps the reason; the manager reads only; the page fits a phone.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

function istDate(days: number): string {
  return new Date(Date.now() + 330 * 60_000 + days * 86_400_000).toISOString().slice(0, 10);
}

test("BDM follow-ups: add, counts, done, cancel, manager read-only, phone width", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm008-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm008-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E8-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Follow College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;

  await page.goto(`/bdm/organizations/${org.id}`);
  await page.getByRole("button", { name: "Add task" }).click();
  await page.getByLabel("Title (required)").fill("Call the principal");
  await page.getByLabel("Due date (IST, required)").fill(istDate(0));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Call the principal")).toBeVisible();

  await page.goto("/bdm/follow-ups");
  await page.getByRole("button", { name: "Add follow-up or task" }).first().click();
  await page.getByRole("radio", { name: "Task" }).check(); // getByLabel("Task") also matches the form "Add follow-up or task"
  await page.getByLabel("Title (required)").fill("Prepare the travel plan");
  await page.getByLabel("Due date (IST, required)").fill(istDate(1));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const tabs = page.getByRole("navigation", { name: "Follow-up lists" });
  await expect(tabs.getByRole("button", { name: "Today (1)" })).toBeVisible();
  await expect(tabs.getByRole("button", { name: "Upcoming (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "College 1" })).toBeVisible();

  await page.getByRole("button", { name: "Done", exact: true }).click(); // not the "Done (n)" tab
  await expect(page.getByText("Marked done.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Book appointment" })).toHaveAttribute("href", `/bdm/appointments/new?organization=${org.id}`);

  await tabs.getByRole("button", { name: "Upcoming (1)" }).click();
  await expect(page.getByRole("button", { name: "No organization 1" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel task" }).click();
  await page.getByLabel("Reason (required)").fill("Trip postponed");
  await page.getByRole("button", { name: "Cancel it" }).click();
  await tabs.getByRole("button", { name: "Cancelled (1)" }).click();
  await expect(page.getByText(/Trip postponed/)).toBeVisible();
  await tabs.getByRole("button", { name: "Done (1)" }).click();
  await expect(page.getByText("Call the principal")).toBeVisible();

  await page.setViewportSize({ width: 360, height: 780 });
  await expect(page.getByRole("heading", { name: "Your follow-ups and tasks" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/follow-ups?bucket=done");
  await expect(page.getByText("Call the principal")).toBeVisible();
  await expect(page.getByRole("button", { name: "Done", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add follow-up or task" })).toHaveCount(0);
});
