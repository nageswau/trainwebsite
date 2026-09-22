import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-011 (DEC-SCOPE-023) -- a Career Counselor runs a Soft Skills batch end to end: create -> enrol -> session + attendance ->
// assessment + score -> certify; the linked parent then sees it in the Parent Portal's Skills section and on the timeline.
// Registers its own throwaway School + Coordinator + Career Counselor + student + parent (dev invite token, like
// sch-roster-parent-invite). The create form is submitted from the keyboard.

test("career counselor runs a Soft Skills batch; the parent sees Skills progress (ENH-011)", async ({ page }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const coordinatorEmail = `enh011-e2e-coord-${unique}@example.local`;
  const counselorEmail = `enh011-e2e-counselor-${unique}@example.local`;
  const schoolName = `E2E ENH-011 School ${unique}`;
  const studentName = `E2E Skills Student ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E ENH-011 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "career_counselor");
  await page.fill("#staff-name", "E2E ENH-011 Counselor");
  await page.fill("#staff-email", counselorEmail);
  await page.selectOption("#staff-schools", { label: schoolName });
  await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");
  await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });

  // Coordinator adds the student with a parent; the dev invite token stands in for the emailed link.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
  const created = await page.request.post("/api/v1/school/students", { data: { full_name: studentName, parent_name: "E2E Skills Parent", parent_email: `enh011-e2e-parent-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const { id: studentId, development_invite_token: inviteToken } = await created.json();
  expect(inviteToken).toBeTruthy();

  // Counselor: create a batch from the keyboard, then run it.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", counselorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/career-counselor/dashboard");
  await page.getByRole("link", { name: "Skills" }).first().click();
  await page.waitForURL("**/school/career-counselor/skills");
  await expect(page.getByText("No skills batches yet.")).toBeVisible();
  await page.getByRole("button", { name: "Create a batch" }).click();
  await expect(page.getByLabel("Title")).toBeFocused();
  await page.keyboard.type("Public speaking");
  await page.getByLabel("Topic (optional)").fill("Presentation");
  await page.getByLabel("Start date").fill("2026-10-01");
  await page.getByLabel("End date (optional)").fill("2026-12-01");
  await page.getByLabel("Title").press("Enter");
  await page.waitForURL(/\/school\/career-counselor\/skills\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: "Public speaking" })).toBeVisible();

  await page.getByRole("group", { name: "Enrol students" }).getByLabel(studentName).check();
  await page.getByRole("button", { name: "Enrol 1 student" }).click();
  await expect(page.getByText("1 student enrolled.")).toBeVisible();

  await page.getByLabel("Session date").fill("2026-10-05");
  await page.getByRole("button", { name: "Add session" }).click();
  await expect(page.getByText(/Session on .* added\./)).toBeVisible();
  await page.getByRole("button", { name: "Mark all present" }).click();
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save attendance" }).click();
  await expect(page.getByText(/Attendance saved for/)).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(studentName) }).getByText("Attended 1 of 1 session")).toBeVisible();

  await page.getByLabel("Assessment name").fill("Speech");
  await page.getByLabel("Maximum score").fill("20");
  await page.getByRole("button", { name: "Add assessment" }).click();
  await expect(page.getByText("Speech added.")).toBeVisible();
  await page.getByLabel(`Score for ${studentName} (out of 20)`).fill("16");
  await page.getByLabel(`Remarks for ${studentName} (optional)`).fill("Pace yourself");
  await page.getByRole("button", { name: "Save scores" }).click();
  await expect(page.getByText("Scores saved for Speech.")).toBeVisible();

  await page.getByRole("button", { name: `Certify ${studentName}` }).click();
  await page.getByRole("button", { name: `Confirm certify ${studentName}` }).click();
  await expect(page.getByText(`${studentName}: Certified.`)).toBeVisible();

  // Parent: accepts the invite, sees the Skills section and the timeline events.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${inviteToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await page.goto(`/school/parent/children/${studentId}`);
  const skills = page.locator(".card", { has: page.getByRole("heading", { name: "Skills", exact: true }) });
  await expect(skills.getByText("Public speaking")).toBeVisible();
  await expect(skills.getByText("Certified")).toBeVisible();
  await expect(skills.getByText("Speech: 16 / 20 — Pace yourself")).toBeVisible();
  await expect(skills.getByText("Not enrolled in a Digital Skills batch yet.")).toBeVisible();
  await expect(page.getByText("Certified in Public speaking")).toBeVisible();
});
