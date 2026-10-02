import { expect, test, type Page } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-017 (DEC-SCOPE-055) AC9 -- a Master assigns a student to a staff member; the staff member sees the unread badge and the notice,
// opens it (marking it read), and the badge is gone on the next page. Also the empty state and a 320 px phone. Unique names per run
// (shared E2E DB).
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function addNoLoginStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

async function addStaff(page: Page, name: string, email: string): Promise<string> {
  await page.goto("/overseas/agent/team");
  const staffForm = page.getByRole("form", { name: "Add a staff member" });
  await staffForm.getByLabel("Full name").fill(name);
  await staffForm.getByLabel("Email").fill(email);
  await staffForm.getByRole("button", { name: "Add staff" }).click();
  const created = await page.getByText(/-S001 created/).textContent();
  return created!.match(/(\S+-S001)/)![1];
}

test("a Master's assignment reaches the staff member as one notice with an unread badge that clears once opened", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn017");
  const staffEmail = `agn017-s-${unique}@example.local`;
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  const code = await addStaff(page, "Neha Notices", staffEmail);

  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/notifications");
  await expect(staff.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
  await expect(staff.getByText(/No notifications yet\./)).toBeVisible();
  await expect(staff.locator(".portal-nav").getByRole("link", { name: "Notifications", exact: true })).toBeVisible();

  const student = `E2E Notice ${stamp()}`;
  await addNoLoginStudent(page, student);
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: `Assign ${student}`, exact: true }).click();
  const choice = page.getByRole("group", { name: `Assign ${student}` });
  await choice.getByLabel("Assign to").selectOption({ label: `${code} · Neha Notices` });
  await choice.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByText(`${student} assigned to ${code} · Neha Notices.`)).toBeVisible();

  await staff.goto("/overseas/agent/dashboard");
  await expect(staff.locator(".portal-nav").getByRole("link", { name: "Notifications 1 unread" })).toBeVisible();
  await staff.locator(".portal-nav").getByRole("link", { name: "Notifications 1 unread" }).click();
  const list = staff.getByRole("list", { name: "Notifications" });
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await expect(list).toContainText("Student assigned to you");
  await expect(list).toContainText("A student is now assigned to you.");
  await expect(list).not.toContainText(student); // no names in a notice (spec §8)

  await list.getByRole("link", { name: "Open: Student assigned to you" }).click();
  await staff.waitForURL("**/overseas/agent/students");
  await expect
    .poll(async () => {
      await staff.goto("/overseas/agent/notifications");
      return staff.locator(".portal-nav .nav-badge").count();
    })
    .toBe(0);
  await expect(staff.getByRole("list", { name: "Notifications" }).getByText("new")).toHaveCount(0);
});

test("the Notifications page fits a 320 px phone and the mobile menu names it", async ({ page }) => {
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn017p");
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/overseas/agent/notifications");
  await expect(page.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.locator("#portal-mobile-nav-panel").getByRole("link", { name: /^Notifications/ })).toBeVisible();
});
