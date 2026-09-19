import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-011 -- Partnership tier entitlements (`DEC-SCOPE-017`). Overseas Admin sets a tier at
// school creation; Coordinator and Principal see the cumulative service list with a real
// usage count wherever a confirmed module produces one, and "Not tracked" (never a
// fabricated 0) for the rest.

test("overseas admin sets a tier, coordinator and principal see real entitlement counts (SCH-011)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `sch011-e2e-coord-${unique}@example.local`;
  const principalEmail = `sch011-e2e-principal-${unique}@example.local`;
  const schoolName = `E2E SCH-011 School ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.selectOption("#school-tier", "bronze");
  await page.fill("#school-coordinator-name", "E2E SCH-011 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const principalInvite = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_principal", full_name: "E2E SCH-011 Principal", email: principalEmail } });
  expect(principalInvite.ok()).toBeTruthy();
  const principalToken = (await principalInvite.json()).development_invite_token;

  await page.goto("/school/coordinator/activities");
  await page.fill("#activity-title", "Career Seminar Day");
  await page.fill("#activity-when", "2027-01-15T10:00");
  await page.selectOption("#activity-type", "career_seminar");
  await page.click('button:has-text("Schedule activity")');
  await expect(page.getByText(/Career Seminar Day scheduled\./)).toBeVisible();

  await page.goto("/school/coordinator/entitlements");
  await expect(page.getByText("Bronze Partner")).toBeVisible();
  const careerSeminarRow = page.locator("tr", { hasText: "Career seminar" });
  await expect(careerSeminarRow.getByRole("cell", { name: "1", exact: true })).toBeVisible();
  const softSkillsRow = page.locator("tr", { hasText: "Soft skills" });
  await expect(softSkillsRow.getByText("Not tracked")).toBeVisible();
  // Bronze tier only -- a Gold/Platinum-only service must not appear at all.
  await expect(page.getByText("IELTS coaching")).toHaveCount(0);

  // Principal accepts their invite and sees the identical figures.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${principalToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");
  await page.goto("/school/principal/entitlements");
  await expect(page.getByText("Bronze Partner")).toBeVisible();
  await expect(page.locator("tr", { hasText: "Career seminar" }).getByRole("cell", { name: "1", exact: true })).toBeVisible();
});
