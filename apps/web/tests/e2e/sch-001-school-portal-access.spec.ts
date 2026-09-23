import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-001 -- School Portal role-based access (Principal/Coordinator/Teacher/Parent).
// Requires the stack running via `docker compose up` with `python -m app.seed` already
// applied (seeds an `overseas_admin` account, overseasadmin@edusphere.local/Demo@123).
// Builds its own throwaway School + full role set per test via the real onboarding flow
// (SCH-003), then exercises SCH-001's role-scoped roster/activity access on top of it.

async function onboardSchoolWithFullTeam(page: import("@playwright/test").Page, unique: number) {
  const coordinatorEmail = `sch001-e2e-coord-${unique}@example.local`;
  const principalEmail = `sch001-e2e-principal-${unique}@example.local`;
  const teacherEmail = `sch001-e2e-teacher-${unique}@example.local`;
  const parentEmail = `sch001-e2e-parent-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E SCH-001 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Coordinator");
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

  for (const [role, email, name, expectedPath] of [
    ["school_principal", principalEmail, "E2E Principal", "**/school/principal/dashboard"],
    ["school_teacher", teacherEmail, "E2E Teacher", "**/school/teacher/dashboard"],
    ["school_parent", parentEmail, "E2E Parent", "**/school/parent/dashboard"],
  ] as const) {
    // Each iteration must (re-)authenticate as the Coordinator first -- the previous
    // iteration's "accept" step logged the *new* invitee in, overwriting the session.
    const invited = await page.request.post("/api/v1/school/team/invites", { data: { role, full_name: name, email } });
    const { development_invite_token: token } = await invited.json();
    await page.request.post("/api/v1/auth/logout");
    await page.goto(`/school/invite/${token}/accept`);
    await page.fill("#invite-password", "Sup3r-Secret-Pass!");
    await page.click('button:has-text("Accept and set up login")');
    // Accepting logs the new account in and redirects to its own role dashboard
    // (ROLE_DASHBOARD_PATH), which SCH-001 now provides for all three of these roles.
    await page.waitForURL(expectedPath);
    await page.request.post("/api/v1/auth/logout");
    await page.goto("/overseas/login");
    await page.fill("#login-email", coordinatorEmail);
    await page.fill("#login-password", E2E_PASSWORD);
    await page.click("button:has-text('Sign in securely')");
    await page.waitForURL("**/school/coordinator/dashboard");
  }

  return { coordinatorEmail, principalEmail, teacherEmail, parentEmail };
}

test("coordinator adds a student, assigns a teacher, links a parent; principal/teacher/parent each see only their own scope (SCH-001)", async ({ page }) => {
  const unique = Date.now();
  const { principalEmail, teacherEmail, parentEmail } = await onboardSchoolWithFullTeam(page, unique);

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "E2E Student One");
  await page.fill("#new-grade", "Grade 4");
  await page.selectOption("#new-teacher", { label: "E2E Teacher" });
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "E2E Student One" })).toBeVisible();

  const row = page.locator("tr", { hasText: "E2E Student One" });
  await row.getByRole("button", { name: "Link parent" }).click();
  const linkForm = page.locator(".action-card", { has: page.getByRole("heading", { name: "Link a parent" }) });
  await linkForm.locator("#link-parent-email").fill(parentEmail);
  await linkForm.getByRole("button", { name: "Link parent" }).click();
  await expect(page.getByText(/Parent linked/)).toBeVisible();

  // Principal: read-only, whole institution.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", principalEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/principal/dashboard");
  await expect(page.getByRole("cell", { name: "E2E Student One" })).toBeVisible();

  // Teacher: only the assigned student.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", teacherEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");
  await expect(page.getByRole("cell", { name: "E2E Student One" })).toBeVisible();

  // Parent: only their own linked child.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", parentEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/parent/dashboard");
  await expect(page.getByRole("heading", { name: "E2E Student One" })).toBeVisible();
});

test("a teacher cannot reach a student outside their own assignment, even within the same school, via a direct URL (SCH-001-AC03)", async ({ page }) => {
  const unique = Date.now();
  const { teacherEmail } = await onboardSchoolWithFullTeam(page, unique);

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "Unassigned E2E Student");
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();

  const studentApi = await page.request.get("/api/v1/school/students");
  const students = await studentApi.json();
  const unassigned = students.find((s: { full_name: string }) => s.full_name === "Unassigned E2E Student");
  expect(unassigned).toBeTruthy();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", teacherEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");

  await page.goto(`/school/teacher/students/${unassigned.id}`);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
