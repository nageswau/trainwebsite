import { expect, test, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-016 -- the School CRM §1 KPI board leads the coordinator's dashboard; the reports page carries the §29 / Part B §14 / §28
// sections (grade filter driven by the keyboard, no page-level horizontal scroll at 320px); a student's page carries the §28
// scorecard; the Edusphere admin sees the cross-school page and a coordinator who opens it is refused. Requires the stack
// running with `python -m app.seed` applied (seeds overseasadmin@edusphere.local/Demo@123). Builds a throwaway school per run.
const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function noPageScroll(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}

test("school dashboards, report sections, scorecard and cross-school analytics are role-scoped (ENH-016)", async ({ page }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(`${new URL(page.url()).pathname}: ${String(error).slice(0, 140)}`));

  // An admin creates a Gold school and its coordinator.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const coordinatorEmail = `enh016-e2e-coord-${unique}@example.local`;
  const schoolName = `E2E ENH-016 School ${unique}`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E ENH-016 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "gold");
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");

  // The coordinator adds one Grade 10 student; the KPI board leads the dashboard.
  await signIn(page, coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const created = await page.request.post("/api/v1/school/students", { data: { full_name: "E2E Analytics Student", grade_or_class: "Grade 10", grade_level: 10 } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).id as string;
  await page.reload();
  await expect(page.getByRole("heading", { name: "School at a glance" })).toBeVisible();
  const students = page.getByRole("region", { name: "Students" });
  await expect(students.getByText("Total Students")).toBeVisible();
  await expect(page.getByText("Not tracked yet").first()).toBeVisible(); // internships stay honest

  // Reports: the three ENH-016 sections render with real data.
  await page.goto("/school/coordinator/reports");
  await expect(page.getByRole("heading", { name: "Grade-wise comparison" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Grade 10" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Student development" })).toBeVisible();
  await expect(page.getByText("No published results yet.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Student progress scorecards" })).toBeVisible();
  await expect(page.getByRole("link", { name: "E2E Analytics Student" })).toBeVisible();

  // Keyboard only: pick "Grade 8" in the filter and submit -- the Grade 10 student drops out, the filter stays in the URL.
  await page.getByLabel("Grade", { exact: true }).focus();
  await page.keyboard.press("ArrowDown");
  await page.getByRole("button", { name: "Show" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/grade=8/);
  await expect(page.getByText("No students match this grade.")).toBeVisible();

  // Phone width: wide tables scroll inside their cards, never the page.
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/school/coordinator/reports");
  await expect(page.getByRole("heading", { name: "Student progress scorecards" })).toBeVisible();
  expect(await noPageScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // The student's own page carries the scorecard.
  await page.goto(`/school/coordinator/students/${studentId}`);
  await expect(page.getByRole("heading", { name: "Progress scorecard" })).toBeVisible();
  await expect(page.getByText("Not tracked yet").first()).toBeVisible(); // scholarship / internship

  // A coordinator who opens the admin page is refused, and the API agrees.
  await page.goto("/overseas/admin/school-analytics");
  await expect(page.getByText("Access unavailable")).toBeVisible();
  expect((await page.request.get("/api/v1/overseas-admin/analytics/summary")).status()).toBe(403);

  // The Edusphere admin sees every school, including this one.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/school-analytics");
  await expect(page.getByRole("heading", { name: "School Analytics" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Outcomes" })).toContainText("Not tracked yet");
  await expect(page.getByRole("table", { name: "Service utilization by school" })).toBeVisible();
  await expect(page.getByRole("link", { name: "School Analytics" }).first()).toBeVisible();

  expect(pageErrors).toEqual([]);
});
