import { test, expect, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-025 -- Student Master fields (DEC-SCOPE-027): coordinator edits the fields and the photo, a teacher reads them,
// a career counsellor records career preferences, and the form works at phone width.
// Requires the stack running with `python -m app.seed` applied (overseasadmin@edusphere.local/Demo@123).
// Registers its own throwaway school, coordinator, teacher, counsellor and student per run.

// A real, decodable 1x1 PNG, so the browser actually renders the authorized image.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function setUp(page: Page, unique: number) {
  const schoolName = `E2E ENH-025 School ${unique}`;
  const coordinatorEmail = `enh025-e2e-coord-${unique}@example.local`;
  const teacherEmail = `enh025-e2e-teacher-${unique}@example.local`;
  const counselorEmail = `enh025-e2e-counselor-${unique}@example.local`;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "career_counselor");
  await page.fill("#staff-name", "E2E Counsellor");
  await page.fill("#staff-email", counselorEmail);
  await page.selectOption("#staff-schools", { label: schoolName });
  await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");
  await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const invited = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Teacher", email: teacherEmail } });
  const { development_invite_token: token } = await invited.json();
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/teacher/dashboard");

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "Asha Rao");
  await page.selectOption("#new-teacher", { label: "E2E Teacher" });
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/added to the roster/)).toBeVisible();
  const href = await page.locator("tr", { hasText: "Asha Rao" }).getByRole("link", { name: "Timeline" }).getAttribute("href");
  const studentId = href!.split("/").pop()!;
  return { coordinatorEmail, teacherEmail, counselorEmail, studentId };
}

test("coordinator records the Student Master fields and photo; teacher reads them; counsellor records career preferences (ENH-025)", async ({ page }) => {
  test.setTimeout(120_000);
  const { teacherEmail, counselorEmail, studentId } = await setUp(page, Date.now());

  // Coordinator: edit the new fields through the grouped form.
  await page.locator("tr", { hasText: "Asha Rao" }).getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#edit-heading")).toBeFocused();
  await page.fill("#edit-section", "A");
  await page.fill("#edit-roll", "7");
  await page.selectOption("#edit-gender", "female");
  await page.fill("#edit-city", "Pune");
  await page.fill("#edit-subjects", "Maths, Physics");
  await page.click('button:has-text("Save changes")');
  await expect(page.getByText("Student updated.")).toBeVisible();
  const row = page.locator("tr", { hasText: "Asha Rao" });
  await expect(row.getByRole("cell", { name: "A", exact: true })).toBeVisible();
  await expect(row.getByRole("cell", { name: "7", exact: true })).toBeVisible();

  // Coordinator: profile + photo on the student page.
  await page.goto(`/school/coordinator/students/${studentId}`);
  await expect(page.getByText("Female")).toBeVisible();
  await expect(page.getByText("Maths, Physics")).toBeVisible();
  await expect(page.getByRole("img", { name: "No photo for Asha Rao" })).toBeVisible();
  await page.setInputFiles("#photo-" + studentId, { name: "asha.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByText("Photo saved.")).toBeVisible();
  const photo = page.getByRole("img", { name: "Photo of Asha Rao" });
  await expect(photo).toBeVisible();
  await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Remove photo" }).click();
  await page.getByRole("button", { name: "Confirm remove" }).click();
  await expect(page.getByRole("img", { name: "No photo for Asha Rao" })).toBeVisible();
  await page.setInputFiles("#photo-" + studentId, { name: "asha.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByText("Photo saved.")).toBeVisible();

  // Teacher (assigned): reads the same profile and photo, with no photo controls.
  await signIn(page, teacherEmail, "Sup3r-Secret-Pass!", "**/school/teacher/dashboard");
  await page.goto(`/school/teacher/students/${studentId}`);
  await expect(page.getByText("Pune")).toBeVisible();
  await expect.poll(() => page.getByRole("img", { name: "Photo of Asha Rao" }).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByLabel(/upload a photo|replace photo/i)).toHaveCount(0);

  // Career counsellor: career preferences for a portfolio student.
  await signIn(page, counselorEmail, E2E_PASSWORD, "**/school/career-counselor/dashboard");
  await page.selectOption("#prefs-student", { value: studentId });
  await page.fill("#prefs-preferred_countries", "Germany, Canada");
  await page.selectOption("#prefs-global", "yes");
  await page.click('button:has-text("Save preferences")');
  await expect(page.getByText("Career preferences saved.")).toBeVisible();
});

test("the roster edit form stacks to one column with no horizontal scroll at phone width (ENH-025)", async ({ page }) => {
  test.setTimeout(120_000);
  await setUp(page, Date.now());
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/school/coordinator/students");
  await page.locator("tr", { hasText: "Asha Rao" }).getByRole("button", { name: "Edit" }).click();
  for (const legend of ["Identity", "Class placement", "Contact", "Studies & interests"]) {
    await expect(page.getByRole("group", { name: legend }).first()).toBeVisible();
  }
  const section = await page.locator("#edit-section").boundingBox();
  const roll = await page.locator("#edit-roll").boundingBox();
  expect(roll!.y).toBeGreaterThan(section!.y); // stacked, not side by side
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
