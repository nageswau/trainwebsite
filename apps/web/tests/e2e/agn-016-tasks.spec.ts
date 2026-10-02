import { expect, test, type Page } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-016 (DEC-SCOPE-051) AC12 -- tasks and follow-ups: a Master adds tasks on the Tasks page (one already overdue), the assigned
// staff member sees and completes theirs, reassignment moves the task, keyboard-only add, the student card, 320 px. Unique names
// per run (shared E2E DB).
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function addNoLoginStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

async function addTask(page: Page, student: string, title: string, due: string) {
  await page.goto("/overseas/agent/tasks");
  await page.getByRole("button", { name: "New task" }).click();
  const form = page.getByRole("group", { name: "New task" });
  await pickFromList(form.getByRole("combobox", { name: "Student" }), student, new RegExp(`^${student} — no login$`));
  await form.getByLabel("Title").fill(title);
  await form.getByLabel("Due").fill(due);
  await form.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByText(`“${title}” added.`)).toBeVisible();
}

async function assign(page: Page, student: string, label: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: `Assign ${student}`, exact: true }).click();
  const choice = page.getByRole("group", { name: `Assign ${student}` });
  await choice.getByLabel("Assign to").selectOption({ label });
  await choice.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByText(`${student} assigned to ${label}.`)).toBeVisible();
}

async function addStaff(page: Page, name: string, email: string, n: string): Promise<string> {
  await page.goto("/overseas/agent/team");
  const staffForm = page.getByRole("form", { name: "Add a staff member" });
  await staffForm.getByLabel("Full name").fill(name);
  await staffForm.getByLabel("Email").fill(email);
  await staffForm.getByRole("button", { name: "Add staff" }).click();
  const created = await page.getByText(new RegExp(`-S${n} created`)).textContent();
  return created!.match(new RegExp(`(\\S+-S${n})`))![1];
}

test("Master adds tasks, staff complete theirs, reassignment moves a task, the KPI counts open tasks", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn016");
  const priyaEmail = `agn016-p-${unique}@example.local`;
  const rahulEmail = `agn016-r-${unique}@example.local`;
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  const priya = await addStaff(page, "Priya Tasks", priyaEmail, "001");
  const rahul = await addStaff(page, "Rahul Tasks", rahulEmail, "002");

  const student = `E2E Task ${stamp()}`;
  await addNoLoginStudent(page, student);
  await assign(page, student, `${priya} · Priya Tasks`);
  await addTask(page, student, "Collect the CAS letter", "2031-10-05T09:30");
  await addTask(page, student, "Chase the bank letter", "2020-01-01T09:00"); // already overdue: allowed, flagged

  const list = page.getByRole("list", { name: "Tasks" });
  const overdue = list.getByRole("listitem").filter({ hasText: "Chase the bank letter" });
  await expect(overdue.getByText("Overdue", { exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "Task views" }).getByRole("link", { name: "Overdue" }).click();
  await expect(page.getByRole("link", { name: "Overdue" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("list", { name: "Tasks" })).toContainText("Chase the bank letter");
  await expect(page.getByRole("list", { name: "Tasks" })).not.toContainText("Collect the CAS letter");

  await page.goto("/overseas/agent/dashboard");
  await expect(page.getByText("Pending actions")).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, priyaEmail);
  await signIn(staff, priyaEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/tasks");
  const mine = staff.getByRole("list", { name: "Tasks" });
  await expect(mine).toContainText("Collect the CAS letter");
  await mine.getByRole("button", { name: "Mark “Chase the bank letter” done" }).click();
  await expect(staff.getByText("“Chase the bank letter” marked done.")).toBeVisible();
  await expect(mine).not.toContainText("Chase the bank letter");

  await assign(page, student, `${rahul} · Rahul Tasks`); // the open task follows the student (T1)
  await staff.reload();
  await expect(staff.getByText("No open tasks.")).toBeVisible();
  await staff.context().close();

  const other = await (await browser.newContext()).newPage();
  await adminActivate(other.request, rahulEmail);
  await signIn(other, rahulEmail, E2E_PASSWORD);
  await other.goto("/overseas/agent/tasks");
  await expect(other.getByRole("list", { name: "Tasks" })).toContainText("Collect the CAS letter");
  await other.context().close();
});

test("a task can be added with the keyboard only, and appears on the student's card", async ({ page }) => {
  const student = `E2E Kbd ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await addNoLoginStudent(page, student);
  await page.goto("/overseas/agent/tasks");
  await page.getByRole("button", { name: "New task" }).focus();
  await page.keyboard.press("Enter");
  const form = page.getByRole("group", { name: "New task" });
  await pickFromList(form.getByRole("combobox", { name: "Student" }), student, new RegExp(`^${student} — no login$`));
  await form.getByLabel("Title").focus();
  await page.keyboard.type("Book the visa slot");
  await page.keyboard.press("Tab");
  await form.getByLabel("Due").fill("2031-11-01T10:00");
  await form.getByRole("button", { name: "Add task" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("“Book the visa slot” added.")).toBeVisible();
  await expect(page.getByRole("button", { name: "New task" })).toBeFocused();

  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: `View ${student}`, exact: true }).click();
  const card = page.getByRole("region", { name: "Tasks" });
  await expect(card).toContainText("Book the visa slot");
});

test("no horizontal scroll on the Tasks page at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await page.goto("/overseas/agent/tasks");
  await expect(page.getByRole("heading", { name: "Tasks & follow-ups", level: 2 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
