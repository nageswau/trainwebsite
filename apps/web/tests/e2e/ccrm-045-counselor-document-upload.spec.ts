import { test, expect, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ccrm-045 (DEC-SCOPE-318) -- the counselor uploads a passport for a walk-in student with no application and an offer letter against
// an application, from the student 360's Documents tab; the student sees both at once (Documents, Offer Letters) and can download them.
// Requires the stack running with `python -m app.seed` applied; the spec makes its own counselor and student.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");

async function noSideScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

test("a counselor uploads documents for a walk-in student, who sees them at once (ccrm-045)", async ({ page, request }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const counselorEmail = `ccrm045-cns-${unique}@example.local`;
  const studentEmail = `ccrm045-s-${unique}@example.local`;

  expect((await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } })).ok()).toBeTruthy();
  const counselor = await createAndActivate(request, "/api/v1/admin/users", { email: counselorEmail, full_name: "Upload Counselor", role: "counselor", division: "overseas" });
  const student = await createAndActivate(request, "/api/v1/admin/users", { email: studentEmail, full_name: `Upload Student ${unique}`, role: "overseas_student", division: "overseas" });
  expect((await request.put(`/api/v1/admin/users/${student.id}/counselor`, { data: { counselor_id: counselor.id } })).ok()).toBeTruthy();

  // Counselor: a walk-in with no application -- a passport, not tied to any application (AC1).
  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  await page.goto(`/overseas/counselor/students/${student.id}?tab=documents`);
  const form = page.getByRole("form", { name: "Upload a document" });
  await expect(form.getByLabel("Application")).toHaveCount(0); // no application to choose yet
  await expect(form.getByLabel("Document type").locator("option", { hasText: "Offer letter" })).toHaveCount(0);
  await form.getByLabel("Document type").selectOption("Passport");
  await form.getByLabel("File").setInputFiles({ name: "passport.pdf", mimeType: "application/pdf", buffer: PDF });
  await form.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByText("Uploaded. The student can see it in their Documents.")).toBeVisible();
  const passport = page.locator(".s360-list li", { hasText: "Passport" });
  await expect(passport.getByText(/Not linked to an application/)).toBeVisible();
  await expect(passport.getByRole("button", { name: /Download/ })).toBeVisible(); // AC5

  // A wrong file type is refused with the server's message (AC3).
  await form.getByLabel("Document type").selectOption("CV");
  await form.getByLabel("File").setInputFiles({ name: "cv.pdf", mimeType: "application/pdf", buffer: Buffer.from("plain text") });
  await form.getByRole("button", { name: "Upload document" }).click();
  await expect(page.locator(".form-error", { hasText: "Upload a PDF, JPEG or PNG file" })).toBeVisible();

  // An application, then an offer letter against it (AC2).
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: student.id, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  await page.reload();
  await form.getByLabel("Document type").selectOption("Offer letter");
  await expect(form.getByLabel("Application")).toHaveValue((await app.json()).id);
  await form.getByLabel("File").setInputFiles({ name: "offer.pdf", mimeType: "application/pdf", buffer: PDF });
  await form.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByText("Uploaded. The student can see it in their Documents.")).toBeVisible();
  await expect(page.locator(".s360-list li", { hasText: "Offer letter" })).toBeVisible();

  // History names the uploader (AC6).
  await page.goto(`/overseas/counselor/students/${student.id}?tab=history`);
  await expect(page.locator(".s360-list li", { hasText: "Uploaded: Passport" }).getByText(/Upload Counselor/)).toBeVisible();

  for (const width of [768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/overseas/counselor/students/${student.id}?tab=documents`);
    await expect(form).toBeVisible();
    await noSideScroll(page);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // Student: both documents in Documents, the offer letter in Offer Letters with a download.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, studentEmail, E2E_PASSWORD, "/overseas/student/dashboard");
  await page.goto("/overseas/student/documents");
  const mine = page.locator(".action-card", { has: page.getByRole("heading", { name: "Your Documents" }) });
  await expect(mine.getByRole("heading", { name: "Passport" })).toBeVisible();
  await expect(mine.getByRole("heading", { name: "Offer letter" })).toBeVisible();

  await page.goto("/overseas/student/offer-letters");
  await expect(page.getByRole("cell", { name: "offer.pdf" })).toBeVisible();
  const letters = page.locator(".action-card", { has: page.getByRole("heading", { name: "Your offer letters" }) });
  await expect(letters.getByRole("heading", { name: "Offer letter" })).toBeVisible();
  await expect(letters.getByRole("heading", { name: "Passport" })).toHaveCount(0);
  const link = page.waitForResponse((r) => r.url().includes("/api/v1/workflows/overseas/documents/") && r.url().endsWith("/download"));
  await letters.getByRole("button", { name: "Download" }).click();
  const response = await link;
  expect(response.status()).toBe(200);
  expect((await response.json()).url).toContain("/api/v1/files/");

  expect(consoleErrors.filter((e) => !e.includes("status of 415"))).toEqual([]); // the 415 is the refused file above
});
