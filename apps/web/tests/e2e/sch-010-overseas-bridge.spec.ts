import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, activateWithToken, createAndActivateFromUi } from "./helpers/welcome";

// SCH-010 -- School->Overseas bridge (`DEC-SCOPE-018`). A Counselor (never
// school_coordinator, per direct user decision) looks a School student up by their
// business-facing Student ID and starts a real Overseas application for them. No UI exists
// yet for creating a Counselor account (only Manage Users' edit/deactivate actions do), so
// that one fixture step uses the real admin API directly, matching this codebase's own
// established convention (see ADM-001's own spec) -- everything under test here (the
// lookup + bridge panel) is driven through the UI.

test("counselor links a School student to a real Overseas application via their Student ID (SCH-010)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `sch010-e2e-coord-${unique}@example.local`;
  const counselorEmail = `sch010-e2e-counselor-${unique}@example.local`;
  const schoolName = `E2E SCH-010 School ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E SCH-010 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  const counselorCreated = await page.request.post("/api/v1/admin/users", {
    data: { full_name: "E2E SCH-010 Counselor", email: counselorEmail, division: "overseas", role: "counselor" },
  });
  expect(counselorCreated.ok()).toBeTruthy();
  await activateWithToken(page.request, (await counselorCreated.json()).development_welcome_token);

  // A real university to link against -- created here, while still logged in as Overseas
  // Admin, since only overseas_admin/super_admin may call this endpoint.
  const universityName = `E2E SCH-010 University ${unique}`;
  const universityCreated = await page.request.post("/api/v1/admin/universities", {
    data: { country_slug: "usa", slug: `e2e-sch010-university-${unique}`, name: universityName },
  });
  expect(universityCreated.ok()).toBeTruthy();

  // Coordinator adds a student and reads their Student ID off the roster.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "E2E SCH-010 Student");
  await page.click('button:has-text("Add student")');
  const studentRow = page.getByRole("row", { name: /E2E SCH-010 Student/ });
  await expect(studentRow).toBeVisible();
  const studentCode = (await studentRow.locator("td").first().textContent())?.trim();
  expect(studentCode).toMatch(/^[0-9A-F]{8}$/);

  // Counselor looks the student up by Student ID and starts the bridge application.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", counselorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");

  await page.goto("/overseas/counselor/school-applications");
  await page.fill("#bridge-student-code", studentCode!);
  await page.click('button:has-text("Look up")');
  await expect(page.getByText(new RegExp(`E2E SCH-010 Student.*${schoolName}`))).toBeVisible();

  // The option label is "{name} ({city})" -- this university was created via the admin API
  // with no city, so it renders with empty parens.
  await page.selectOption("#bridge-university", { label: `${universityName} ()` });
  await page.fill("#bridge-intake", "Fall 2027");
  await page.click('button:has-text("Start application")');
  await expect(page.getByText(/Application started for E2E SCH-010 Student\./)).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(`E2E SCH-010 Student.*${studentCode}.*${universityName}`) })).toBeVisible();

  // The Coordinator's own read-only overview reflects the linked application.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const studentHref = await page.goto("/school/coordinator/students").then(() => page.getByRole("row", { name: /E2E SCH-010 Student/ }).getByRole("link", { name: "Timeline" }).getAttribute("href"));
  const studentId = studentHref?.split("/").pop();
  const overview = await page.request.get(`/api/v1/school/students/${studentId}/overview`);
  expect(overview.status()).toBe(200);
  const overviewBody = await overview.json();
  expect(overviewBody.global_education.status).toBe("linked");
  expect(overviewBody.global_education.applications[0].university_name).toBe(universityName);
});
