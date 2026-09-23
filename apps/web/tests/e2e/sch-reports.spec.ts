import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// School Coordinator/Principal Reports module -- real, computed-from-live-data charts
// (grade-wise bar chart, service-delivery completion rings, activity/attendance stats).
// Builds its own throwaway school + roster + records via the real onboarding/roster/
// service-delivery flows, then confirms both roles see the same real numbers, and that
// Teacher/Parent are denied the page entirely.

test("coordinator and principal see real report figures; teacher is denied (School Reports)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch-rpt-e2e-coord-${unique}@example.local`;
  const teacherEmail = `sch-rpt-e2e-teacher-${unique}@example.local`;
  const principalEmail = `sch-rpt-e2e-principal-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Reports School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Reports Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: entitled to every service
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  // Two students in the same grade, a Teacher assigned to one, so the bar chart and the
  // "assigned Teacher" line both have real, non-trivial numbers. The Teacher must accept
  // their invite before assign_teacher_email can resolve them -- an assigned_teacher_email
  // is validated against a real school_teacher User, not a pending invite.
  const invitedTeacher = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Reports Teacher", email: teacherEmail } });
  expect(invitedTeacher.status()).toBe(201);
  const teacherToken = (await invitedTeacher.json()).development_invite_token;
  const invitedPrincipal = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_principal", full_name: "E2E Reports Principal", email: principalEmail } });
  const principalToken = (await invitedPrincipal.json()).development_invite_token;

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${teacherToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/teacher/dashboard");

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "Report Student One");
  await page.fill("#new-grade", "Grade 6");
  await page.selectOption("#new-teacher", { label: "E2E Reports Teacher" });
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();

  await page.fill("#new-full-name", "Report Student Two");
  await page.fill("#new-grade", "Grade 6");
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();

  await page.goto("/school/coordinator/reports");
  await expect(page.getByText("Students by grade")).toBeVisible();
  await expect(page.getByText("Grade 6")).toBeVisible();
  await expect(page.getByText("1 of 2 students have an assigned Teacher.")).toBeVisible();
  await expect(page.getByText("Service delivery completion")).toBeVisible();
  await expect(page.getByText("Career guidance")).toBeVisible();
  await expect(page.getByText("Activities & attendance")).toBeVisible();

  // Teacher is denied the report entirely, even via a direct URL. They set their own
  // password when accepting the invite above -- not the Coordinator-seeded default.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", teacherEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");
  await page.goto("/school/coordinator/reports");
  await expect(page.getByText("Access unavailable")).toBeVisible();

  // Principal accepts their invite and sees the identical real numbers (own institution,
  // read-only), not the Coordinator's own nav-restricted view.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${principalToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");
  await page.click('a:has-text("View full reports")');
  await page.waitForURL("**/school/principal/reports");
  await expect(page.getByText("Grade 6")).toBeVisible();
  await expect(page.getByText("1 of 2 students have an assigned Teacher.")).toBeVisible();
});
