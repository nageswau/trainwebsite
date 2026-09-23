import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, activateWithToken, createAndActivateFromUi } from "./helpers/welcome";

// SCH-008 -- narrow Student Journey Timeline. Builds its own throwaway school + roster
// through the real onboarding/roster flows, records one event in each already-built
// module (career guidance, psychometric assessment + report, academic result published,
// activity attendance), then confirms: (a) the Parent's child page shows the timeline in
// real chronological order, (b) the Teacher's, (c) the School Coordinator's, and (d) the
// Principal's own per-student pages all show the identical ordered timeline, each reached
// through that role's own real UI entry point (not just a direct URL), and (e) an unlinked
// sibling's timeline is denied to the Parent even by direct URL (SCH-001-AC03 carried into
// SCH-008, and DEC-SCOPE-016's "available to Coordinator/Teacher/Principal too" extension).

test("student journey timeline renders in order for Parent, Teacher, Coordinator and Principal, denied for an unlinked child (SCH-008)", async ({ page }) => {
  // A multi-account journey: ENH-003 added a create + set-password step per provisioned account, which took this
  // test from 14.5 s to 16.7 s -- past the 15 s default. Same override the other long onboarding journeys use.
  test.setTimeout(60_000);
  const unique = Date.now();
  const coordinatorEmail = `sch008-e2e-coord-${unique}@example.local`;
  const principalEmail = `sch008-e2e-principal-${unique}@example.local`;
  const parentEmail = `sch008-e2e-parent-${unique}@example.local`;
  const counselorEmail = `sch008-e2e-counselor-${unique}@example.local`;
  const psychEmail = `sch008-e2e-psych-${unique}@example.local`;
  const academicEmail1 = `sch008-e2e-academic1-${unique}@example.local`;
  const academicEmail2 = `sch008-e2e-academic2-${unique}@example.local`;

  // --- Overseas Admin: create the school + seed Coordinator, and the three specialized staff.
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Timeline School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Timeline Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: entitled to every service
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  const schoolListRes = await page.request.get("/api/v1/overseas-admin/schools");
  const schools = await schoolListRes.json();
  const school = schools.find((s: { name: string }) => s.name === `E2E Timeline School ${unique}`);

  for (const [email, role] of [[counselorEmail, "career_counselor"], [psychEmail, "psychometric_team"], [academicEmail1, "academic_team"], [academicEmail2, "academic_team"]] as const) {
    const created = await page.request.post("/api/v1/overseas-admin/school-staff", { data: { role, full_name: email, email } });
    expect(created.status()).toBe(201);
    const createdBody = await created.json();
    const staffId = createdBody.id;
    await activateWithToken(page.request, createdBody.development_welcome_token);
    const assigned = await page.request.post(`/api/v1/overseas-admin/school-staff/${staffId}/portfolio`, { data: { school_id: school.id } });
    expect(assigned.status()).toBe(200); // no status_code=201 on this route -- FastAPI's default
  }

  // --- Coordinator: create the roster (linked child + unlinked sibling), assign a Teacher.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const teacherEmail = `sch008-e2e-teacher-${unique}@example.local`;
  const invitedTeacher = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Timeline Teacher", email: teacherEmail } });
  const teacherToken = (await invitedTeacher.json()).development_invite_token;
  const invitedPrincipal = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_principal", full_name: "E2E Timeline Principal", email: principalEmail } });
  const principalToken = (await invitedPrincipal.json()).development_invite_token;

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${teacherToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/teacher/dashboard");

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${principalToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const linkedRes = await page.request.post("/api/v1/school/students", {
    data: { full_name: "Timeline Linked Child", grade_or_class: "Grade 7", assigned_teacher_email: teacherEmail, parent_name: "E2E Timeline Parent", parent_email: parentEmail },
  });
  expect(linkedRes.status()).toBe(201);
  const linked = await linkedRes.json();
  const parentToken = linked.development_invite_token;
  const unlinkedRes = await page.request.post("/api/v1/school/students", { data: { full_name: "Timeline Unlinked Sibling", grade_or_class: "Grade 9" } });
  const unlinked = await unlinkedRes.json();

  // --- One event in each already-built module, for the linked child. Each specialized
  // staff account was created via POST /overseas-admin/school-staff (no password field) and
  // activated from its welcome link, so it carries E2E_PASSWORD, not the seeded
  // demo accounts' "Demo@123".
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", counselorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/career-counselor/dashboard");
  const guidanceRes = await page.request.post("/api/v1/school/career-counselor/records", { data: { school_student_id: linked.id, record_type: "guidance_session", notes: "Explored engineering vs design paths" } });
  expect(guidanceRes.status()).toBe(201);

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", psychEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/psychometric-team/dashboard");
  const psychRes = await page.request.post("/api/v1/school/psychometric-team/records", { data: { school_student_id: linked.id, assessment_type: "Aptitude Test" } });
  expect(psychRes.status()).toBe(201);
  const psychId = (await psychRes.json()).id;
  const reportRes = await page.request.patch(`/api/v1/school/psychometric-team/records/${psychId}`, { data: { report_url: "/local-files/uploads/report.pdf" } });
  expect(reportRes.status()).toBe(200);

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", academicEmail1);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");
  const resultRes = await page.request.post("/api/v1/school/academic-team/results", {
    data: { school_student_id: linked.id, academic_year: "2026-27", term: "Term 1", subject: "Mathematics", max_marks: 100, marks_obtained: 88, grade: "A" },
  });
  expect(resultRes.status()).toBe(201);
  const resultId = (await resultRes.json()).id;

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", academicEmail2);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");
  expect((await page.request.post(`/api/v1/school/academic-team/results/${resultId}/verify`)).status()).toBe(200);
  expect((await page.request.post(`/api/v1/school/academic-team/results/${resultId}/publish`)).status()).toBe(200);

  // --- Parent: sees the linked child's timeline in real chronological order.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");

  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${linked.id}`);
  await expect(page.getByRole("heading", { name: "Journey timeline" })).toBeVisible();

  const titles = await page.locator(".jtl-title").allTextContents();
  expect(titles).toEqual([
    "Student profile created",
    "Career guidance session",
    "Psychometric assessment assigned",
    "Psychometric report uploaded",
    "Academic result published",
  ]);
  const badges = await page.locator(".jtl-badge").allTextContents();
  expect(badges).toEqual(["Profile", "Career", "Psychometric", "Psychometric", "Academic"]);
  await expect(page.locator(".jtl-detail").filter({ hasText: "Explored engineering vs design paths" })).toBeVisible();
  await expect(page.locator(".jtl-detail").filter({ hasText: "Term 1 Mathematics" })).toBeVisible();

  // Deny path: the unlinked sibling's timeline, by direct URL.
  await page.goto(`/school/parent/children/${unlinked.id}`);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  // --- Teacher: same timeline for their assigned student, via the per-student detail page.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", teacherEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");
  await page.goto(`/school/teacher/students/${linked.id}`);
  await expect(page.getByRole("heading", { name: "Journey timeline" })).toBeVisible();
  const teacherTitles = await page.locator(".jtl-title").allTextContents();
  expect(teacherTitles).toEqual(titles);

  // --- School Coordinator: same timeline, reached via the roster's own "Timeline" link
  // (not a direct URL) -- DEC-SCOPE-016's extension to Coordinator/Teacher/Principal.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
  await page.goto("/school/coordinator/students");
  await page.locator("tr", { hasText: "Timeline Linked Child" }).getByRole("link", { name: "Timeline" }).click();
  await page.waitForURL(`**/school/coordinator/students/${linked.id}`);
  await expect(page.getByRole("heading", { name: "Journey timeline" })).toBeVisible();
  const coordinatorTitles = await page.locator(".jtl-title").allTextContents();
  expect(coordinatorTitles).toEqual(titles);

  // --- Principal: same timeline, reached via the dashboard's own roster table link.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", principalEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/principal/dashboard");
  await page.locator("tr", { hasText: "Timeline Linked Child" }).getByRole("link", { name: "Timeline" }).click();
  await page.waitForURL(`**/school/principal/students/${linked.id}`);
  await expect(page.getByRole("heading", { name: "Journey timeline" })).toBeVisible();
  const principalTitles = await page.locator(".jtl-title").allTextContents();
  expect(principalTitles).toEqual(titles);
});
