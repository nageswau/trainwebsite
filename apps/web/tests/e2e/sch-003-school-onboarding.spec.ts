import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-003 -- School partner onboarding (Admin-created, Coordinator-seeded invites).
// Requires the stack running via `docker compose up` with `python -m app.seed` already
// applied (seeds an `overseas_admin` account, overseasadmin@edusphere.local/Demo@123).
// Registers its own throwaway School + Coordinator + invited Principal per test run.

test("overseas admin creates a school + seed coordinator, who invites a principal, who accepts and signs in (SCH-003)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch003-e2e-coord-${unique}@example.local`;
  const principalEmail = `sch003-e2e-principal-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E School ${unique}`);
  await page.fill("#school-city", "Testville");
  await page.fill("#school-coordinator-name", "E2E Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: entitled to every service
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  await expect(page.getByRole("cell", { name: `E2E School ${unique}` })).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
  await page.goto("/school/coordinator/team");
  await expect(page.getByText(/just you so far/)).toBeVisible();

  await page.selectOption("#invite-role", "school_principal");
  await page.fill("#invite-name", "E2E Principal");
  await page.fill("#invite-email", principalEmail);
  await page.click('button:has-text("Send invite")');
  await expect(page.getByText(/Invite sent/)).toBeVisible();
  await expect(page.getByRole("cell", { name: principalEmail })).toBeVisible();

  // Development-only token exposure lets this test complete the accept step without a
  // real inbox -- same convention as AUTH-001's password-reset E2E coverage.
  const inviteRow = page.locator("tr", { hasText: principalEmail });
  await expect(inviteRow).toBeVisible();

  const teamResponse = await page.request.get("/api/v1/school/team");
  const team = await teamResponse.json();
  const invite = team.pending_invites.find((i: { email: string }) => i.email === principalEmail);
  expect(invite).toBeTruthy();

  const inviteDetail = await page.request.post("/api/v1/school/team/invites", {
    data: { role: "school_teacher", full_name: "E2E Teacher (token probe)", email: `sch003-e2e-teacher-${unique}@example.local` },
  });
  const inviteData = await inviteDetail.json();
  const token = inviteData.development_invite_token;
  expect(token).toBeTruthy();

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  // Accepting logs the account in and redirects to its own role dashboard
  // (ROLE_DASHBOARD_PATH) -- SCH-001 now gives school_teacher a real one.
  await page.waitForURL("**/school/teacher/dashboard");

  await page.goto("/overseas/login");
  await page.fill("#login-email", `sch003-e2e-teacher-${unique}@example.local`);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");
  await expect(page.getByText("Invalid credentials")).not.toBeVisible();
});

test("a consumed invite token shows an honest, specific message, not a generic broken-link page (SCH-003-AC06)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch003-e2e-coord2-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E School B ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Coordinator B");
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

  const invited = await page.request.post("/api/v1/school/team/invites", {
    data: { role: "school_parent", full_name: "E2E Parent", email: `sch003-e2e-parent-${unique}@example.local` },
  });
  const { development_invite_token: token } = await invited.json();

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");

  // Reuse the same (now-consumed) token.
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await expect(page.getByText(/already been used, expired, or was revoked/)).toBeVisible();
});

// ENH-009 -- School Profile field coverage. The success text below is
// AdminSchoolCreatePanel.tsx's real wording ("School created. School code XXXXXXXX.
// Coordinator account ready for ...", via welcomeLinkFeedback()), not a generic
// "School created." -- School ID is an 8-char uppercase hex code (unique_student_code()).
test("School ID is generated and shown on both the create panel and the Partner Schools list (ENH-009)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch009-e2e-coord-${unique}@example.local`;
  const schoolName = `E2E Profile School ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-branch", "North Campus");
  await page.selectOption("#school-board", "CBSE");
  await page.fill("#school-coordinator-name", "E2E Profile Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: entitled to every service
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");

  const successMessage = page.getByText(/School created\. School code [A-Z0-9]{8}\./);
  await expect(successMessage).toBeVisible();
  const schoolIdText = await successMessage.textContent();
  const schoolId = schoolIdText!.match(/School code ([A-Z0-9]{8})/)![1];

  // Scope to the row for this test's own school (not a bare page-wide cell lookup) so a
  // leftover "North Campus" from an earlier manual QA session against this same stack can't
  // produce a false match or a strict-mode multiple-match failure.
  const schoolRow = page.locator("tr", { hasText: schoolName });
  await expect(schoolRow).toBeVisible();
  await expect(schoolRow.getByRole("cell", { name: schoolId })).toBeVisible();
  await expect(schoolRow.getByRole("cell", { name: "North Campus" })).toBeVisible();
});

test("admin can look up a school by its School ID and edit its profile (ENH-009)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch009-e2e-edit-${unique}@example.local`;
  const schoolName = `E2E Edit School ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E Edit Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: entitled to every service
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  const successMessage = page.getByText(/School created\. School code [A-Z0-9]{8}\./);
  await expect(successMessage).toBeVisible();
  const schoolIdText = await successMessage.textContent();
  const schoolId = schoolIdText!.match(/School code ([A-Z0-9]{8})/)![1];

  // AdminSchoolCreatePanel and AdminSchoolEditPanel both mount on this same page, so the
  // lookup-by-code panel's own field/button IDs (#school-lookup-code, #edit-branch) are used
  // rather than a label-text query, which would ambiguously match both panels' "Branch" labels.
  await page.fill("#school-lookup-code", schoolId);
  await page.click('button:has-text("Look up")');
  await expect(page.locator("#edit-branch")).toBeVisible();
  await page.fill("#edit-branch", "South Campus");
  await page.click('button:has-text("Save changes")');
  await expect(page.getByText("School profile updated.")).toBeVisible();

  await page.reload();
  const editedRow = page.locator("tr", { hasText: schoolName });
  await expect(editedRow.getByRole("cell", { name: "South Campus" })).toBeVisible();
});
