import { expect, test, type Page } from "@playwright/test";

// AGN-004 -- a Master's students with no login: create, duplicate warning, edit, archive, unarchive; keyboard-only; 320 px.
// Uses the seeded demo agent (a Master of an active agency). Staff flows need AGN-002's staff logins and are validated after that
// merge (spec §12). Unique names per run: the E2E database is shared and keeps rows.

async function signInAsDemoAgent(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
}

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function addStudent(page: Page, name: string, email?: string) {
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  if (email) await form.getByLabel("Email").fill(email);
  await form.getByRole("button", { name: "Save student" }).click();
  return form;
}

test("a Master adds, edits, archives and restores a student with no login (AGN-004-AC01/03/04/08)", async ({ page }) => {
  const id = stamp();
  const name = `E2E Student ${id}`;
  const email = `agn004-${id}@example.local`;
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  const students = page.getByRole("list", { name: "Students" });

  await addStudent(page, name, email);
  await expect(page.getByText(`${name} added.`)).toBeVisible();

  // Same email in another case: the within-agency duplicate warning, then Save anyway.
  const twin = await addStudent(page, `${name} Twin`, email.toUpperCase());
  await expect(twin.getByRole("alert")).toContainText("already exists in your agency");
  await twin.getByRole("button", { name: "Save anyway" }).click();
  await expect(page.getByText(`${name} Twin added.`)).toBeVisible();

  // The search is debounced: wait until the list holds exactly this run's two students before acting on a card.
  await page.getByLabel("Search students").fill(id);
  await expect(students.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("region", { name: "Student list" })).toHaveAttribute("aria-busy", "false");
  await students.getByRole("button", { name: `View ${name}`, exact: true }).click();
  const detail = page.getByRole("region", { name, exact: true });
  await detail.getByRole("button", { name: "Edit" }).click();
  await detail.getByLabel("Preferred country").fill("Ireland");
  await detail.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText(`${name} saved.`)).toBeVisible();
  await expect(detail.getByText("Ireland")).toBeVisible();

  await students.getByRole("button", { name: `Archive ${name}`, exact: true }).click();
  await students.getByRole("button", { name: "Confirm archive" }).click();
  await expect(page.getByText(`${name} archived.`)).toBeVisible();
  await expect(students.getByRole("heading", { name, exact: true })).toHaveCount(0);

  await page.getByLabel("Show archived").check();
  await students.getByRole("button", { name: `Unarchive ${name}`, exact: true }).click();
  await students.getByRole("button", { name: "Confirm unarchive" }).click();
  await expect(page.getByText(`${name} restored.`)).toBeVisible();
});

test("keyboard only: add a student (AGN-004-AC13)", async ({ page }) => {
  const name = `Keyboard ${stamp()}`;
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("form", { name: "Add student" }).getByLabel("Full name (required)").focus();
  await page.keyboard.type(name);
  await page.keyboard.press("Enter");
  await expect(page.getByText(`${name} added.`)).toBeVisible();
});

test("320 px: the Students page has no horizontal overflow (AGN-004-AC13)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  await expect(page.getByRole("heading", { name: "Students", level: 3 })).toBeVisible();
  await expect(page.getByRole("list", { name: "Students" }).or(page.getByText(/No students yet/))).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
