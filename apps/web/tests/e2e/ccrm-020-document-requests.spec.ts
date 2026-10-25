import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ccrm-020 (DEC-SCOPE-265) -- the nehn-037 acceptance: the counselor requests "IELTS scorecard" from a checklist item (R2), the student
// sees the due date and uploads against it, a rejection reopens it with the counselor's note (R1), the student uploads again, the
// counselor accepts and the item leaves "missing". Requires the stack running with `python -m app.seed` applied; the spec makes its own
// counselor, student and application.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

test("a counselor's document request goes from requested to verified (ccrm-020)", async ({ page, request }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const counselorEmail = `ccrm020-cns-${unique}@example.local`;
  const studentEmail = `ccrm020-s-${unique}@example.local`;

  // Set-up through the API: an Overseas Admin makes both logins and links the student to the counselor (csc-005).
  expect((await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } })).ok()).toBeTruthy();
  const counselor = await createAndActivate(request, "/api/v1/admin/users", { email: counselorEmail, full_name: "Request Counselor", role: "counselor", division: "overseas" });
  const student = await createAndActivate(request, "/api/v1/admin/users", { email: studentEmail, full_name: `Request Student ${unique}`, role: "overseas_student", division: "overseas" });
  expect((await request.put(`/api/v1/admin/users/${student.id}/counselor`, { data: { counselor_id: counselor.id } })).ok()).toBeTruthy();

  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: student.id, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  const appId = (await app.json()).id as string;
  const checklist = `/api/v1/workflows/overseas/applications/${appId}/checklist`;
  expect((await page.request.post(checklist)).status()).toBe(201);
  expect((await page.request.post(`${checklist}/items`, { data: { document_type: "English test", label: "IELTS scorecard" } })).status()).toBe(201);

  // Counselor: request the missing item from the student, from the checklist row.
  await page.goto("/overseas/counselor/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: `Request Student ${unique}` }).first();
  await card.getByRole("button", { name: "Document checklist" }).click();
  const item = card.getByRole("region", { name: "Document checklist" }).locator("li", { hasText: "IELTS scorecard" });
  await item.getByRole("button", { name: "Request from student" }).click();
  await item.getByLabel("Due date for IELTS scorecard").fill(day(10));
  await item.getByLabel("Note to the student (optional)").fill("Academic, 6.5 overall");
  await item.getByRole("button", { name: "Send request" }).click();
  await expect(item.getByText(/Requested from the student · due/)).toBeVisible();
  await expect(item.getByText("Requested", { exact: true })).toBeVisible();

  // Student: sees the due date and the note, uploads against the request.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, studentEmail, E2E_PASSWORD, "/overseas/student/dashboard");
  await page.goto("/overseas/student/documents");
  const requested = page.locator(".action-card", { has: page.getByRole("heading", { name: "Requested documents" }) });
  const row = requested.locator("li", { hasText: "IELTS scorecard" });
  await expect(row.getByText(/Due /)).toBeVisible();
  await expect(row.getByText("Academic, 6.5 overall")).toBeVisible();
  await row.getByLabel("File for IELTS scorecard").setInputFiles({ name: "ielts.pdf", mimeType: "application/pdf", buffer: PDF });
  await row.getByRole("button", { name: "Upload" }).click();
  await expect(requested.getByText(/IELTS scorecard uploaded/)).toBeVisible();
  await expect(requested.getByText("No documents are requested from you right now.")).toBeVisible();

  // Counselor: rejects the upload (the existing review route) -- the request is open again, with the reason, on the 360.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  const requests = `/api/v1/counselor/students/${student.id}/document-requests`;
  const first = (await (await page.request.get(requests)).json()).items[0].document.id as string;
  expect((await page.request.patch(`/api/v1/workflows/overseas/documents/${first}/verify`, { data: { verification_status: "reupload_required", notes: "The scan is cut off" } })).ok()).toBeTruthy();
  await page.goto(`/overseas/counselor/students/${student.id}?tab=documents`);
  const panel = page.getByRole("region", { name: "Document requests" });
  await expect(panel.getByText("Reopened after review: The scan is cut off")).toBeVisible();

  // Student: uploads again against the same request.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, studentEmail, E2E_PASSWORD, "/overseas/student/dashboard");
  await page.goto("/overseas/student/documents");
  await expect(row.getByText("Please upload a new file: The scan is cut off")).toBeVisible();
  await row.getByLabel("File for IELTS scorecard").setInputFiles({ name: "ielts-full.pdf", mimeType: "application/pdf", buffer: PDF });
  await row.getByRole("button", { name: "Upload" }).click();
  await expect(requested.getByText(/IELTS scorecard uploaded/)).toBeVisible();

  // Counselor: accepts it -- the checklist item is Verified and nothing is missing.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  const second = (await (await page.request.get(requests)).json()).items[0].document.id as string;
  expect((await page.request.patch(`/api/v1/workflows/overseas/documents/${second}/verify`, { data: { verification_status: "verified" } })).ok()).toBeTruthy();
  await page.goto(`/overseas/counselor/students/${student.id}?tab=documents`);
  await expect(panel.locator("li", { hasText: "IELTS scorecard" }).getByText(/ielts-full\.pdf — Verified/)).toBeVisible();
  await page.goto("/overseas/counselor/applications");
  await card.getByRole("button", { name: "Document checklist" }).click();
  await expect(card.getByText("1 of 1 required complete")).toBeVisible();
  await expect(item.getByText("Verified", { exact: true })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
