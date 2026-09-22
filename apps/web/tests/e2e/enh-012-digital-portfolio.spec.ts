import { expect, test } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-012 -- docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md AC-01..AC-07.
// Setup mirrors sch-008-student-timeline.spec.ts: seed a school/coordinator/teachers/student/parent
// through the real onboarding APIs, then drive the feature itself (adding an entry) through the real
// UI, since that's what this feature actually is.

test("coordinator adds a portfolio entry via the UI; parent sees it read-only; an unassigned teacher is denied (ENH-012)", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const coordinatorEmail = `enh012-e2e-coord-${unique}@example.local`;
  const parentEmail = `enh012-e2e-parent-${unique}@example.local`;
  const assignedTeacherEmail = `enh012-e2e-teacher-assigned-${unique}@example.local`;
  const outsideTeacherEmail = `enh012-e2e-teacher-outside-${unique}@example.local`;

  // --- Overseas Admin: create the school + seed Coordinator (identical to sch-008's own setup).
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Portfolio School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Portfolio Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  const schoolListRes = await page.request.get("/api/v1/overseas-admin/schools");
  const schools = await schoolListRes.json();
  const school = schools.find((s: { name: string }) => s.name === `E2E Portfolio School ${unique}`);
  expect(school).toBeTruthy();

  // --- Coordinator: invite an assigned teacher and an outside (unassigned) teacher, create the student.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const invitedAssigned = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Assigned Teacher", email: assignedTeacherEmail } });
  const assignedToken = (await invitedAssigned.json()).development_invite_token;
  const invitedOutside = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Outside Teacher", email: outsideTeacherEmail } });
  const outsideToken = (await invitedOutside.json()).development_invite_token;

  for (const token of [assignedToken, outsideToken]) {
    await page.request.post("/api/v1/auth/logout");
    await page.goto(`/school/invite/${token}/accept`);
    await page.fill("#invite-password", "Sup3r-Secret-Pass!");
    await page.click('button:has-text("Accept and set up login")');
    await page.waitForURL("**/school/teacher/dashboard");
  }

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const studentRes = await page.request.post("/api/v1/school/students", {
    data: { full_name: "Portfolio Test Child", grade_or_class: "Grade 7", assigned_teacher_email: assignedTeacherEmail, parent_name: "E2E Portfolio Parent", parent_email: parentEmail },
  });
  expect(studentRes.status()).toBe(201);
  const student = await studentRes.json();
  const parentToken = student.development_invite_token;

  // --- Coordinator: reach the student via the real roster link (not a direct URL), read the starting
  // percentage, add an entry through the real form, confirm the list and percentage both update.
  await page.goto("/school/coordinator/students");
  await page.locator("tr", { hasText: "Portfolio Test Child" }).getByRole("link", { name: "Timeline" }).click();
  await page.waitForURL(`**/school/coordinator/students/${student.id}`);
  await expect(page.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();
  const startingPercent = Number((await page.locator(".pf-meter-label").textContent())?.match(/\d+/)?.[0] ?? "0");

  await page.getByRole("button", { name: "Add award" }).click();
  await page.getByLabel("Title").fill("Regional Science Fair — 1st place");
  await page.getByLabel("Organization (optional)").fill("State Science Council");
  await page.getByRole("button", { name: "Save" }).click();
  // exact: true -- the entry's Edit/Delete buttons also contain this title text (e.g. "Edit Regional
  // Science Fair — 1st place"), so a non-exact match is ambiguous; only the <strong> title matches exactly.
  await expect(page.getByText("Regional Science Fair — 1st place", { exact: true })).toBeVisible();
  const updatedPercent = Number((await page.locator(".pf-meter-label").textContent())?.match(/\d+/)?.[0] ?? "0");
  expect(updatedPercent).toBeGreaterThan(startingPercent);

  // --- Parent: sees the same entry, with zero write controls anywhere in the portfolio card (AC-05).
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${student.id}`);
  await expect(page.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();
  await expect(page.getByText("Regional Science Fair — 1st place")).toBeVisible();
  await expect(page.locator(".pf-panel").getByRole("button", { name: /add|edit|delete/i })).toHaveCount(0);

  // --- Outside teacher: not assigned to this student, denied the student's page entirely (AC-06/AC-07).
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", outsideTeacherEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");
  await page.goto(`/school/teacher/students/${student.id}`);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
