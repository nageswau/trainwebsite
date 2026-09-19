import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-009 -- Test Preparation (IELTS/SAT) and Foreign Language Classes, delivered by the
// existing Academic Team role (`DEC-SCOPE-018`: no new role was created for these two
// modules). Registers its own throwaway School + Coordinator + Academic Team + student,
// then confirms the Academic Team member can start/complete both, and the Coordinator's
// student overview reflects the outcome.

test("academic team starts and completes test prep and language classes; coordinator overview reflects it (SCH-009)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `sch009-e2e-coord-${unique}@example.local`;
  const academicEmail = `sch009-e2e-academic-${unique}@example.local`;
  const schoolName = `E2E SCH-009 School ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E SCH-009 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "academic_team");
  await page.fill("#staff-name", "E2E SCH-009 Academic Team");
  await page.fill("#staff-email", academicEmail);
  await page.selectOption("#staff-schools", { label: schoolName });
  await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");
  await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "E2E SCH-009 Student");
  await page.click('button:has-text("Add student")');
  const studentRow = page.getByRole("row", { name: /E2E SCH-009 Student/ });
  await expect(studentRow).toBeVisible();
  const studentLink = studentRow.getByRole("link", { name: "Timeline" });
  const studentHref = await studentLink.getAttribute("href");
  const studentId = studentHref?.split("/").pop();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", academicEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");

  await page.selectOption("#testprep-student", { label: `E2E SCH-009 Student — ${schoolName}` });
  await page.selectOption("#testprep-type", "ielts");
  await page.fill("#testprep-target", "7.5");
  await page.click('button:has-text("Start preparation")');
  await expect(page.getByText(/IELTS preparation started\./)).toBeVisible();

  const testPrepRow = page.locator("tr", { hasText: "IELTS" });
  await testPrepRow.getByLabel(/Actual score for/).fill("7.0");
  await testPrepRow.getByRole("button", { name: "Record score" }).click();
  await expect(page.getByText(/Result recorded\./)).toBeVisible();
  await expect(testPrepRow.getByText("completed")).toBeVisible();

  await page.selectOption("#language-student", { label: `E2E SCH-009 Student — ${schoolName}` });
  await page.fill("#language-name", "German");
  await page.fill("#language-level", "A1");
  await page.click('button:has-text("Start classes")');
  await expect(page.getByText(/German classes started\./)).toBeVisible();

  const languageRow = page.locator("tr", { hasText: "German" });
  await languageRow.getByRole("button", { name: "Mark certified" }).click();
  await expect(page.getByText(/Marked certified\./)).toBeVisible();
  await expect(languageRow.getByText("certified")).toBeVisible();

  // Coordinator's overview for this exact student reflects both outcomes.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const overview = await page.request.get(`/api/v1/school/students/${studentId}/overview`);
  expect(overview.status()).toBe(200);
  const overviewBody = await overview.json();
  expect(overviewBody.test_prep.status).toBe("completed");
  expect(overviewBody.foreign_language.status).toBe("certified");
});
