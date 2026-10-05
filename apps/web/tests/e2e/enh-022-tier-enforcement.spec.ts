import { test, expect, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-022 (DEC-SCOPE-027) -- a partnership tier is enforced, not only reported. A Bronze school's Coordinator is refused a
// Platinum-only campus visit with the exact server message shown as an alert beside the schedule form (input kept), and can
// still schedule a Bronze career seminar. Repeated at phone width, where the message must be visible where the user acted.

const DENIED = "This school's Bronze partnership does not include Monthly campus visits (requires Platinum or higher).";

async function bronzeCoordinator(page: Page, unique: number): Promise<void> {
  const coordinatorEmail = `enh022-e2e-coord-${unique}@example.local`;
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-022 School ${unique}`);
  await page.selectOption("#school-tier", "bronze");
  await page.fill("#school-coordinator-name", "E2E ENH-022 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
}

async function schedule(page: Page, title: string, category: string): Promise<void> {
  await page.fill("#activity-title", title);
  await page.fill("#activity-when", "2027-01-15T10:00");
  await page.selectOption("#activity-type", category);
  await page.click('button:has-text("Schedule activity")');
}

// QA-022-05: a long "Student — School" option made the counselor's form (and so the page) wider than a phone, pushing the
// refusal off the right edge. The page must fit a 390px screen whatever the option text.
test("the career counselor dashboard fits a phone with long school names (QA-022-05)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const counselorEmail = `enh022-e2e-cc-${unique}@example.local`;
  const schoolName = `E2E ENH-022 Greenfield International Residential Academy ${unique}`;
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.selectOption("#school-tier", "bronze");
  await page.fill("#school-coordinator-name", "E2E ENH-022 Coordinator");
  await page.fill("#school-coordinator-email", `enh022-e2e-coord2-${unique}@example.local`);
  const school = await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "career_counselor");
  await page.fill("#staff-name", "E2E ENH-022 Counselor");
  await page.fill("#staff-email", counselorEmail);
  await page.selectOption("#staff-schools", { label: schoolName });
  await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", `enh022-e2e-coord2-${unique}@example.local`);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
  expect((await page.request.post("/api/v1/school/students", { data: { full_name: `E2E Student With A Long Name ${unique}` } })).ok()).toBeTruthy();
  expect(school.id).toBeTruthy();

  await page.request.post("/api/v1/auth/logout");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/overseas/login");
  await page.fill("#login-email", counselorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/career-counselor/dashboard");
  await expect(page.locator("#career-student option", { hasText: schoolName })).toHaveCount(1);
  const widths = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, screen: window.innerWidth }));
  expect(widths.page).toBeLessThanOrEqual(widths.screen);

  // The (Bronze) refusal is readable where the counselor acted.
  await page.selectOption("#career-student", { index: 1 });
  await page.selectOption("#career-type", "guidance_session");
  await page.fill("#career-notes", "E2E note");
  await page.click('button:has-text("Save record")');
  const alert = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add a record" }) }).getByRole("alert");
  await expect(alert).toContainText("requires Silver or higher");
  await expect(alert).toBeInViewport({ ratio: 1 });
});

for (const viewport of [{ name: "desktop", width: 1280, height: 800 }, { name: "phone", width: 390, height: 844 }]) {
  test(`a Bronze school is refused a Platinum-only activity and keeps its Bronze ones (${viewport.name}, ENH-022)`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await bronzeCoordinator(page, Date.now());
    await page.goto("/school/coordinator/activities");

    await schedule(page, "Campus visit", "campus_visit");
    const scheduleCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Schedule an activity" }) });
    const alert = scheduleCard.getByRole("alert");
    await expect(alert).toHaveText(DENIED);
    await expect(alert).toBeInViewport();
    await expect(page.locator("#activity-title")).toHaveValue("Campus visit");
    await expect(page.getByRole("button", { name: "Schedule activity" })).toBeEnabled();

    await schedule(page, "Career Seminar Day", "career_seminar");
    await expect(scheduleCard.getByRole("status")).toHaveText("Career Seminar Day scheduled.");
    await expect(scheduleCard.getByRole("alert")).toHaveCount(0);
  });
}
