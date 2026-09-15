import { test, expect } from "@playwright/test";

// SCH-003/SCH-001 addenda -- Coordinator activate/deactivate for own-school team
// accounts, and the live Teacher picker replacing the hand-typed email field. Builds its
// own throwaway School + full role set via the real onboarding flow (SCH-003), same
// helper as sch-001-school-portal-access.spec.ts.

async function onboardSchoolWithFullTeam(page: import("@playwright/test").Page, unique: number) {
  const coordinatorEmail = `sch-team-e2e-coord-${unique}@example.local`;
  const principalEmail = `sch-team-e2e-principal-${unique}@example.local`;
  const teacherEmail = `sch-team-e2e-teacher-${unique}@example.local`;
  const parentEmail = `sch-team-e2e-parent-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E SCH-Team School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.click('button:has-text("Create school + seed Coordinator")');
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", "ChangeMe@12345");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  for (const [role, email, name, expectedPath] of [
    ["school_principal", principalEmail, "E2E Principal", "**/school/principal/dashboard"],
    ["school_teacher", teacherEmail, "E2E Teacher", "**/school/teacher/dashboard"],
    ["school_parent", parentEmail, "E2E Parent", "**/school/parent/dashboard"],
  ] as const) {
    const invited = await page.request.post("/api/v1/school/team/invites", { data: { role, full_name: name, email } });
    const { development_invite_token: token } = await invited.json();
    await page.request.post("/api/v1/auth/logout");
    await page.goto(`/school/invite/${token}/accept`);
    await page.fill("#invite-password", "Sup3r-Secret-Pass!");
    await page.click('button:has-text("Accept and set up login")');
    await page.waitForURL(expectedPath);
    await page.request.post("/api/v1/auth/logout");
    await page.goto("/overseas/login");
    await page.fill("#login-email", coordinatorEmail);
    await page.fill("#login-password", "ChangeMe@12345");
    await page.click("button:has-text('Sign in securely')");
    await page.waitForURL("**/school/coordinator/dashboard");
  }

  return { coordinatorEmail, principalEmail, teacherEmail, parentEmail };
}

test("coordinator activates/deactivates a team account, never their own (SCH-003 addendum)", async ({ page }) => {
  const unique = Date.now();
  await onboardSchoolWithFullTeam(page, unique);

  await page.goto("/school/coordinator/team");
  const teacherRow = page.locator("tr", { hasText: "E2E Teacher" });
  await expect(teacherRow.getByText("Active")).toBeVisible();
  await expect(teacherRow.getByRole("button", { name: "Deactivate" })).toBeVisible();

  // The Coordinator's own row has no toggle at all.
  const coordinatorRow = page.locator("tr", { hasText: "Coordinator" });
  await expect(coordinatorRow.getByRole("button", { name: /Deactivate|Reactivate/ })).toHaveCount(0);

  await teacherRow.getByRole("button", { name: "Deactivate" }).click();
  await expect(teacherRow.getByText("Inactive")).toBeVisible();
  await expect(teacherRow.getByRole("button", { name: "Reactivate" })).toBeVisible();

  await teacherRow.getByRole("button", { name: "Reactivate" }).click();
  await expect(teacherRow.getByText("Active")).toBeVisible();
});

test("deactivated teacher drops out of the new-student picker but stays visible on an already-assigned student (SCH-001 addendum)", async ({ page }) => {
  const unique = Date.now();
  await onboardSchoolWithFullTeam(page, unique);

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "Picker Regression Student");
  await page.selectOption("#new-teacher", { label: "E2E Teacher" });
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();

  await page.goto("/school/coordinator/team");
  await page.locator("tr", { hasText: "E2E Teacher" }).getByRole("button", { name: "Deactivate" }).click();
  await expect(page.locator("tr", { hasText: "E2E Teacher" }).getByText("Inactive")).toBeVisible();

  await page.goto("/school/coordinator/students");
  // New-student form: the deactivated teacher is not offered.
  await expect(page.locator("#new-teacher option", { hasText: "E2E Teacher" })).toHaveCount(0);

  // Edit form for the already-assigned student: still shows the teacher, labeled inactive.
  await page.locator("tr", { hasText: "Picker Regression Student" }).getByRole("button", { name: "Edit" }).click();
  const editSelect = page.locator("#edit-teacher");
  await expect(editSelect.locator("option", { hasText: "E2E Teacher (inactive)" })).toHaveCount(1);
  await expect(editSelect).toHaveValue(/.+/);
});
