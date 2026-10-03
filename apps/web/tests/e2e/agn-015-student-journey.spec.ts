import { expect, test, type Page } from "@playwright/test";

// AGN-015 -- a Master opens a student and reads the nine-step Journey and the complete history; counseling saved here shows up in
// both; the tracker fits a 320 px phone. Uses the seeded demo agent (a Master of an active agency). Unique names per run: the E2E
// database keeps rows.

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function signInAsDemoAgent(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
}

// The search is debounced: wait until the list holds exactly this run's student before opening it (the AGN-006 helper).
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

test("a new student's Journey and history match what was recorded (AGN-015)", async ({ page }) => {
  const name = `E2E Journey ${stamp()}`;
  await signInAsDemoAgent(page);
  const detail = await addAndOpenStudent(page, name);

  const journey = detail.getByRole("region", { name: "Journey", exact: true });
  const steps = journey.getByRole("list", { name: "Student steps" });
  await expect(steps.getByRole("listitem")).toHaveCount(4);
  await expect(steps.getByRole("listitem").first()).toContainText("Done");
  await expect(steps.locator("[aria-current='step']")).toContainText("Counseling");
  await expect(journey.getByText("No applications yet.")).toBeVisible();

  await detail.getByRole("button", { name: "Show history" }).click();
  const history = detail.getByRole("list", { name: "Student history" });
  await expect(history.getByRole("listitem")).toHaveCount(1);
  await expect(history).toContainText("Student created");

  // Counseling saved but not completed -> the tracker reads "In progress" and the history gains one event with the field names.
  const counseling = detail.getByRole("region", { name: "Counseling" });
  await counseling.getByRole("button", { name: "Record counseling" }).click();
  await counseling.getByLabel("Career interest").fill("Data science");
  await counseling.getByRole("button", { name: "Save counseling" }).click();
  await expect(page.getByText(`Counseling saved for ${name}.`)).toBeVisible();

  await page.reload();
  const after = await openStudent(page, name);
  await expect(after.getByRole("list", { name: "Student steps" }).locator("[aria-current='step']")).toContainText("In progress");
  await after.getByRole("button", { name: "Show history" }).click();
  const events = after.getByRole("list", { name: "Student history" }).getByRole("listitem");
  await expect(events).toHaveCount(2);
  await expect(events.first()).toContainText("Counseling saved");
  await expect(events.first()).toContainText("career interest");
});

test("the Journey fits a 320 px phone with no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  const name = `E2E Journey Phone ${stamp()}`;
  await signInAsDemoAgent(page);
  const detail = await addAndOpenStudent(page, name);
  await expect(detail.getByRole("list", { name: "Student steps" })).toBeVisible();
  await detail.getByRole("button", { name: "Show history" }).click();
  await expect(detail.getByRole("list", { name: "Student history" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
