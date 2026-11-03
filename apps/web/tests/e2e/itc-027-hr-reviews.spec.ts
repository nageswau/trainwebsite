import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// itc-027 (DEC-SCOPE-354): a student shares a resume with HR, which opens one review; the IT Admin hands it to a (throwaway) HR user on
// the HR Reviews page; that HR user finds it in their Review Queue and asks for changes with internal notes; the counselor sees the stage,
// owner and next action (never the notes) and the student sees only "Action required". Throwaway users, so no seeded link moves.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const SECRET = "Internal: weak SQL, thin project section";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const reviewCard = (page: Page) => page.locator("section[aria-labelledby=student-hr-review-heading]");

test("a shared resume opens an HR review that HR works and the counselor and student follow", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const studentName = `Itc Review Student ${stamp}`;
  const hrName = `Itc Reviewer ${stamp}`;

  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const student = await createAndActivate(page.request, "/api/v1/admin/users", { role: "it_student", division: "it", full_name: studentName, email: `itc027-s-${stamp}@example.local` });
  const counselor = await createAndActivate(page.request, "/api/v1/admin/users", { role: "counselor", division: "it", full_name: `Itc Review Counselor ${stamp}`, email: `itc027-c-${stamp}@example.local` });
  expect((await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id, reason: "itc-027 e2e" } })).status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");

  // The student shares a resume with HR: the review opens at "Resume received".
  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/profile");
  await page.locator("#student-resume-file").setInputFiles({ name: `cv-${stamp}.pdf`, mimeType: "application/pdf", buffer: PDF });
  await page.locator("section[aria-labelledby=student-resume-heading]").getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.locator("section[aria-labelledby=student-resume-heading]").getByRole("status")).toContainText("uploaded.");
  await page.goto("/it/student/placement-status");
  await expect(reviewCard(page)).toContainText("Resume received");
  await page.request.post("/api/v1/auth/logout");

  // The IT Admin hands the review to a throwaway HR user -- created only now, so round-robin cannot already have picked them.
  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const hr = await createAndActivate(page.request, "/api/v1/admin/users", { role: "hr_team", division: "it", full_name: hrName, email: `itc027-h-${stamp}@example.local` });
  await page.goto("/it/admin/hr-reviews");
  const row = page.getByRole("row", { name: new RegExp(studentName) });
  await row.getByLabel(`Reassign ${studentName}`).selectOption({ label: hrName });
  await row.getByRole("button", { name: "Assign" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${studentName}'s review is now with ${hrName}.` })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // HR: the queue lists it; the review asks for changes with internal notes.
  await signIn(page, hr.email, E2E_PASSWORD, "/it/hr/dashboard");
  await page.goto("/it/hr/queue");
  await page.getByRole("table", { name: "Review queue" }).getByRole("link", { name: studentName }).click();
  await page.waitForURL(`**/it/hr/students/${student.id}`);
  await page.getByLabel("Stage").selectOption("changes_requested");
  await page.getByLabel("Skills match the course").check();
  await page.getByLabel(/Skill-gap notes/).fill(SECRET);
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByText("Review saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel(/Skill-gap notes/)).toHaveValue(SECRET);
  await page.request.post("/api/v1/auth/logout");

  // The counselor: stage, owner and next action, never the notes.
  await signIn(page, counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/students/${student.id}/profile`);
  await expect(reviewCard(page)).toContainText("Changes requested");
  await expect(reviewCard(page)).toContainText(hrName);
  await expect(reviewCard(page)).toContainText("Student to upload an updated resume");
  await expect(page.getByText(SECRET)).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  // The student: the safe label only; the HR API is closed to them.
  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/placement-status");
  await expect(reviewCard(page)).toContainText("Action required: update your resume");
  await expect(page.getByText(SECRET)).toHaveCount(0);
  expect((await page.request.get("/api/v1/hr/review-tasks")).status()).toBe(403);
});
