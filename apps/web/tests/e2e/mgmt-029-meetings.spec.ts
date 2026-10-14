import { expect, test, type Page } from "@playwright/test";

import { createAndActivate, E2E_PASSWORD } from "./helpers/welcome";

// mgmt-029 (EVID-017 §29, spec MM1-MM14; AC): a partner schedules a partner meeting that started an hour ago with a staff member,
// records the minutes, adds a decision and a task from them, and the meeting shows the chain with "0 of 2 completed". The staff member
// sees the meeting (never the minutes) in Management tasks and completes the task; the meeting then shows "1 of 2 completed". The staff
// user is created through the admin API so the test owns every row it checks.

const PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

/** The datetime-local value (IST) of a moment `minutes` from now. */
const istInput = (minutes: number) => new Date(Date.now() + minutes * 60_000 + 330 * 60_000).toISOString().slice(0, 16);

test("signed out, /management/meetings sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/meetings");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fmeetings$/);
});

test("meeting → minutes → decision → task → completion, rolled up on the meeting", async ({ browser }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const title = `Partner meeting e2e-${stamp}`;
  const task = `Send the draft MoU e2e-${stamp}`;

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, "superadmin@edusphere.local");
  const staffUser = await createAndActivate(admin.request, "/api/v1/admin/users", {
    role: "partnership_head", division: "global", full_name: `Meeting Member ${stamp}`, email: `mgmt029-${stamp}@example.local`,
  });
  const member = `Meeting Member ${stamp} (Partnership Head)`;

  const partner = await (await browser.newContext()).newPage();
  await signIn(partner, "partner.one@edusphere.local");
  await partner.goto("/management");
  await partner.getByRole("link", { name: "Meetings" }).first().click();
  await expect(partner.getByRole("heading", { level: 2, name: "Management meetings" })).toBeVisible();
  await expect(partner.getByRole("heading", { name: "Today's meetings" })).toBeVisible();
  await partner.getByRole("link", { name: "New meeting" }).click();
  await partner.getByLabel("Title").fill(title);
  await partner.getByLabel("Kind").selectOption({ label: "Partner meeting" });
  await partner.getByLabel("Date and time (IST)").fill(istInput(-60));
  await partner.getByLabel("Meeting link (optional)").fill("https://meet.example.com/partners");
  await partner.getByLabel("Find a participant").fill(`Meeting Member ${stamp}`);
  await partner.getByRole("checkbox", { name: member }).check();
  await partner.getByLabel("Agenda (optional)").fill("1. Japan agreement\n2. Next review");
  await partner.getByRole("button", { name: "Schedule meeting" }).click();
  await expect(partner.getByRole("heading", { level: 2, name: title })).toBeVisible();
  await expect(partner.getByText("No decisions or tasks yet")).toBeVisible();

  await partner.getByRole("textbox", { name: "Minutes" }).fill("Agreed to proceed with the Japan agreement.");
  await partner.getByRole("button", { name: "Save minutes" }).click();
  await expect(partner.getByText("Minutes saved.")).toBeVisible();

  await partner.getByLabel("Decision", { exact: true }).fill("Proceed with Japan agreement");
  await partner.getByLabel("Person responsible (optional)").selectOption({ label: member });
  await partner.getByRole("button", { name: "Add decision" }).click();
  await expect(partner.getByRole("listitem", { name: "Proceed with Japan agreement" })).toBeVisible();

  await partner.getByLabel("Task", { exact: true }).fill(task);
  await partner.getByLabel("Owner").selectOption({ label: member });
  await partner.getByLabel("Deadline", { exact: true }).fill(istInput(24 * 60).slice(0, 10));
  await partner.getByRole("button", { name: "Add task" }).click();
  await expect(partner.getByText(`Task: ${task}`)).toBeVisible();
  await expect(partner.getByText("0 of 2 completed")).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await signIn(staff, staffUser.email, E2E_PASSWORD);
  await staff.goto("/account/management-tasks");
  await expect(staff.getByRole("heading", { name: "Meetings" })).toBeVisible();
  await expect(staff.getByText(title)).toBeVisible();
  await expect(staff.getByText("Agreed to proceed")).toHaveCount(0); // never the minutes
  await staff.getByLabel(`Status of “${task}”`).selectOption("completed");
  await staff.getByRole("button", { name: "Update status" }).first().click();
  await expect(staff.getByText("Status updated.")).toBeVisible();
  await staff.goto("/management/meetings");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  await partner.reload();
  await expect(partner.getByText("1 of 2 completed")).toBeVisible();
});
