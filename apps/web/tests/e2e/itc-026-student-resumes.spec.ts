import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// itc-026 (DEC-SCOPE-350): the IT student uploads a resume (a renamed .exe is refused) and a private draft; their IT counselor uploads a
// new version from the student record; HR sees only the shared versions and downloads one; a trainer has no route. A throwaway IT
// student and counselor, so no other spec's counselor link on the seeded student is moved while it runs.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const EXE = Buffer.concat([Buffer.from("MZ"), Buffer.alloc(300)]);

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const card = (page: Page) => page.locator("section[aria-labelledby=student-resume-heading]");

async function uploadResume(page: Page, name: string, buffer: Buffer, mimeType = "application/pdf") {
  await page.locator("#student-resume-file").setInputFiles({ name, mimeType, buffer });
  await card(page).getByRole("button", { name: "Upload", exact: true }).click();
}

test("student, counselor and HR resume versions with an audited download", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();

  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const student = await createAndActivate(page.request, "/api/v1/admin/users", { role: "it_student", division: "it", full_name: `Itc Resume Student ${stamp}`, email: `itc026-s-${stamp}@example.local` });
  const counselor = await createAndActivate(page.request, "/api/v1/admin/users", { role: "counselor", division: "it", full_name: `Itc Resume ${stamp}`, email: `itc026-c-${stamp}@example.local` });
  expect((await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id, reason: "itc-026 e2e" } })).status()).toBe(200);
  await page.goto("/it/admin/students");
  await expect(page.getByRole("heading", { name: "Resume upload limit" })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // − a renamed executable is refused; + a PDF shared with HR, then a private draft.
  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/profile");
  await expect(card(page).getByRole("heading", { name: "Resume" })).toBeVisible();
  await uploadResume(page, "cv.pdf", EXE);
  await expect(card(page).locator(".form-error[role=alert]")).toHaveText("Upload a PDF, DOC or DOCX file");
  await uploadResume(page, `shared-${stamp}.pdf`, PDF);
  await expect(card(page).getByRole("status")).toContainText("uploaded.");
  await page.getByLabel("Share with HR").uncheck();
  await uploadResume(page, `private-${stamp}.pdf`, PDF);
  await expect(card(page).getByRole("status")).toContainText("uploaded.");
  await page.reload();
  await expect(card(page).locator("li").first()).toContainText(`private-${stamp}.pdf`);
  await expect(card(page).locator("li").first()).toContainText("Not shared with HR");
  await expect(card(page).getByText(`shared-${stamp}.pdf`)).toBeVisible(); // the older version is kept
  await page.request.post("/api/v1/auth/logout");

  // + the counselor uploads a new version on the student's behalf.
  await signIn(page, counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/students/${student.id}/profile`);
  await uploadResume(page, `counselor-${stamp}.pdf`, PDF);
  await expect(card(page).getByRole("status")).toContainText("uploaded.");
  await expect(card(page).locator("li").first()).toContainText(`counselor-${stamp}.pdf`);
  await expect(card(page).locator("li").first()).toContainText(`Itc Resume ${stamp} (counselor)`);
  await page.request.post("/api/v1/auth/logout");

  // HR: shared versions only, no upload; a download arrives as an attachment.
  await signIn(page, "hr@edusphere.local", "Demo@123", "/it/hr/dashboard");
  await page.goto(`/it/hr/students/${student.id}`);
  await expect(card(page).locator("li").first()).toContainText(`counselor-${stamp}.pdf`);
  await expect(card(page).getByText(`private-${stamp}.pdf`)).toHaveCount(0);
  await expect(page.locator("#student-resume-file")).toHaveCount(0);
  const [download] = await Promise.all([page.waitForEvent("download"), card(page).locator("li a").first().click()]);
  expect(download.suggestedFilename()).toMatch(/^resume-.+-v\d+\.pdf$/);
  await page.request.post("/api/v1/auth/logout");

  // − a trainer has no route to a student's resumes.
  await signIn(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  expect((await page.request.get(`/api/v1/admin/it/students/${student.id}/resumes`)).status()).toBe(403);
  expect((await page.request.get("/api/v1/it/me/resumes")).status()).toBe(403);
});
