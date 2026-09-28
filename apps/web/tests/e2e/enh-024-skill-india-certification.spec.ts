import { expect, test } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-024 -- docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md AC-01, AC-02, AC-03, AC-13, AC-14.
// Setup mirrors enh-012-digital-portfolio.spec.ts: seed a school/coordinator/teacher/student/parent through the real onboarding
// APIs, then drive the feature itself (recording and certifying a Skill India certification) through the real UI.

test("coordinator records and certifies a Skill India certification; it shows on the portfolio and 360°; the parent sees it read-only (ENH-024)", async ({ page }) => {
  test.setTimeout(90_000);
  const unique = Date.now();
  const coordinatorEmail = `enh024-e2e-coord-${unique}@example.local`;
  const parentEmail = `enh024-e2e-parent-${unique}@example.local`;
  const teacherEmail = `enh024-e2e-teacher-${unique}@example.local`;

  // --- Overseas Admin: create a Platinum school + seed Coordinator (as enh-012).
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Skill India School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Skill India Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: entitled to digital portfolio creation
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  // --- Coordinator: invite the assigned teacher, create the student (with a parent invite).
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const invited = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Skill India Teacher", email: teacherEmail } });
  const teacherToken = (await invited.json()).development_invite_token;
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

  const studentRes = await page.request.post("/api/v1/school/students", {
    data: { full_name: "Skill India Test Child", grade_or_class: "Grade 9", assigned_teacher_email: teacherEmail, parent_name: "E2E Skill India Parent", parent_email: parentEmail },
  });
  expect(studentRes.status()).toBe(201);
  const student = await studentRes.json();
  const parentToken = student.development_invite_token;

  // --- Coordinator: add a Skill India certification (enrolled) through the real form (AC-01, AC-13).
  await page.goto("/school/coordinator/students");
  await page.locator("tr", { hasText: "Skill India Test Child" }).getByRole("link", { name: "Timeline" }).click();
  await page.waitForURL(`**/school/coordinator/students/${student.id}`);
  await expect(page.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();

  await page.getByRole("button", { name: "Add certification" }).click();
  await page.getByLabel("Title").fill("Retail Sales Associate");
  // QA24-05: the checkbox's clickable area (its label row) meets the 24x24 px minimum target size (WCAG 2.2, 2.5.8).
  const skillIndiaTarget = await page.locator("label[for=pf-skill-india]").boundingBox();
  expect(skillIndiaTarget!.height).toBeGreaterThanOrEqual(24);
  expect(skillIndiaTarget!.width).toBeGreaterThanOrEqual(24);
  await page.getByRole("checkbox", { name: "Skill India certification" }).check();
  await page.getByLabel("Issuing body (optional)").fill("Retailers Association's Skill Council of India");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Choose a status.")).toBeVisible(); // client check, nothing sent
  await expect(page.locator("#pf-cert-status")).toBeFocused();
  await page.selectOption("#pf-cert-status", "enrolled");
  await page.getByRole("button", { name: "Save" }).click();

  const card = page.locator(".pf-entry", { hasText: "Retail Sales Associate" });
  await expect(card.getByText("Skill India", { exact: true })).toBeVisible();
  await expect(card.getByText("Enrolled", { exact: true })).toBeVisible();

  // --- Coordinator: certify it; certified needs a number and issue date (AC-03).
  await card.getByRole("button", { name: "Edit Retail Sales Associate" }).click();
  await page.selectOption("#pf-cert-status", "certified");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Enter the certificate number.")).toBeVisible();
  await page.fill("#pf-cert-number", "SI-2026-0001");
  await page.fill("#pf-cert-issued", "2026-05-01");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText("Certified", { exact: true })).toBeVisible();
  await expect(card.getByText("Certificate no. SI-2026-0001")).toBeVisible();

  // --- 360°: the Certificates tab shows the same details (AC-02).
  await page.goto(`/school/coordinator/students/${student.id}/360?tab=certificates`);
  const panel = page.getByRole("tabpanel");
  await expect(panel.getByText("Retail Sales Associate", { exact: true })).toBeVisible();
  await expect(panel.getByText("Certificate no. SI-2026-0001")).toBeVisible();
  await expect(panel.getByText("Certified", { exact: true })).toBeVisible();

  // --- Phone width: the details line wraps, no horizontal page scroll (AC-14).
  await page.setViewportSize({ width: 320, height: 720 });
  await expect(panel.getByText("Certificate no. SI-2026-0001")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // --- Parent: sees the certified entry, with no write controls in the portfolio (AC-02).
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${student.id}`);
  const parentCard = page.locator(".pf-entry", { hasText: "Retail Sales Associate" });
  await expect(parentCard.getByText("Skill India", { exact: true })).toBeVisible();
  await expect(parentCard.getByText("Certificate no. SI-2026-0001")).toBeVisible();
  await expect(page.locator(".pf-panel").getByRole("button", { name: /add|edit|delete/i })).toHaveCount(0);
});
