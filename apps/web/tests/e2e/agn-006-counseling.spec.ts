import { expect, test, type Page } from "@playwright/test";

// AGN-006 -- a Master records a student's counseling, reloads and reads it back; a negative budget is refused on the field; the form
// fits a 320 px phone. Uses the seeded demo agent (a Master of an active agency). Unique names per run: the E2E database keeps rows.

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function signInAsDemoAgent(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
}

// The search is debounced: wait until the list holds exactly this run's student before opening it.
async function openStudent(page: Page, name: string) {
  const students = page.getByRole("list", { name: "Students" });
  await page.getByLabel("Search students").fill(name);
  await expect(students.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("region", { name: "Student list" })).toHaveAttribute("aria-busy", "false");
  await students.getByRole("button", { name: `View ${name}`, exact: true }).click();
  return page.getByRole("region", { name, exact: true });
}

async function addAndOpenStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
  return openStudent(page, name);
}

test("a Master records counseling and reads it back after a reload (AGN-006-AC01/AC11)", async ({ page }) => {
  const name = `E2E Counseling ${stamp()}`;
  await signInAsDemoAgent(page);
  const detail = await addAndOpenStudent(page, name);
  const counseling = detail.getByRole("region", { name: "Counseling" });
  await expect(counseling.getByText("Counseling not recorded yet.")).toBeVisible();
  await counseling.getByRole("button", { name: "Record counseling" }).click();

  await counseling.getByLabel("Amount").fill("-500");
  await counseling.getByRole("button", { name: "Save counseling" }).click();
  await expect(counseling.getByText("Budget cannot be negative")).toBeVisible();
  await expect(counseling.getByLabel("Amount")).toBeFocused();

  await counseling.getByLabel("Counseling completed").check();
  await counseling.getByLabel("Career interest").fill("Data science");
  await counseling.getByLabel("Course preference").fill("MSc Data Science");
  await counseling.getByLabel("Country preference").fill("Ireland");
  await counseling.getByLabel("Amount").fill("25,00,000");
  await counseling.getByLabel("Remarks").fill("Needs scholarship options.");
  await counseling.getByRole("button", { name: "Save counseling" }).click();
  await expect(page.getByText(`Counseling saved for ${name}.`)).toBeVisible();

  await page.reload();
  const after = (await openStudent(page, name)).getByRole("region", { name: "Counseling" });
  await expect(after.getByText(/^Yes — /)).toBeVisible();
  await expect(after.getByText("₹25,00,000.00")).toBeVisible();
  await expect(after.getByText("MSc Data Science")).toBeVisible();
  await expect(after.getByText("Needs scholarship options.")).toBeVisible();
});

test("the counseling form fits a 320 px phone with no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  const name = `E2E Phone ${stamp()}`;
  await signInAsDemoAgent(page);
  const detail = await addAndOpenStudent(page, name);
  await detail.getByRole("button", { name: "Record counseling" }).click();
  await expect(detail.getByLabel("Amount")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
