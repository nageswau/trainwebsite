import { test, expect, type APIRequestContext } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-003 -- staff start on the student journey only; their Master switches Reports and Verify documents on and off, and the
// change shows on the staff member's next page load. Requires the stack running with `python -m app.seed` applied (seeded
// universities). A fresh overseas student is registered per run, so a re-run never meets the duplicate-application rule (409).

async function agencyDocument(request: APIRequestContext, scratch: APIRequestContext, unique: number, staffMemberId: string) {
  const studentEmail = `agn003-st-${unique}@example.local`;
  const registered = await scratch.post("/api/v1/auth/register", { data: { email: studentEmail, password: "Sup3r-Secret-Pass!", full_name: `AGN003 Student ${unique}`, division: "overseas", account_type: "student" } });
  expect(registered.status()).toBe(201);
  // purpose=link matches an email only when typed in full (AGN-001 D2 as revised).
  const found = await (await request.get(`/api/v1/lookups/overseas-students?q=${encodeURIComponent(studentEmail)}&purpose=link`)).json();
  const studentId = found.items[0].id;
  const link = await request.post("/api/v1/workflows/overseas/agent/students", { data: { student_id: studentId } });
  expect(link.status()).toBe(201);
  // AGN-004 G4 (adopted by AGN-003 on merging `main`): staff only reach students assigned to them, so the Master assigns this one.
  const assigned = await request.post(`/api/v1/workflows/overseas/agent/crm/students/${(await link.json()).id}/assign`, { data: { member_id: staffMemberId } });
  expect(assigned.status()).toBe(200);
  const universities = await (await request.get("/api/v1/public/universities")).json();
  const application = await request.post("/api/v1/workflows/overseas/applications", { data: { university_id: universities[0].id, student_id: studentId } });
  expect(application.status()).toBe(201);
  const applicationId = (await application.json()).id;
  const doc = await request.post("/api/v1/workflows/overseas/documents", { data: { student_id: studentId, application_id: applicationId, document_type: "AGN003 Passport", file_url: "uploads/agn003-e2e.pdf" } });
  expect(doc.status()).toBe(201);
}

test("a Master switches a staff member's Reports and Verify permissions (AGN-003)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn003");
  const staffEmail = `agn003-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  const created = await page.request.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "Tau Staff", email: staffEmail } });
  expect(created.status()).toBe(201);
  const scratch = await browser.newContext(); // the student's own registration cookies stay out of the Master's and staff's sessions
  await agencyDocument(page.request, scratch.request, unique, (await created.json()).member.id);
  await scratch.close();

  const staffContext = await browser.newContext();
  const staff = await staffContext.newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);

  // Student journey only: no Reports link, the page refuses, no review queue.
  await expect(staff.getByRole("link", { name: "Reports", exact: true })).toHaveCount(0);
  await staff.goto("/overseas/agent/reports");
  await expect(staff.getByText("Your agency Master hasn't given you access to reports")).toBeVisible();
  await staff.goto("/overseas/agent/documents");
  await expect(staff.getByRole("heading", { name: "Document Verification" })).toHaveCount(0);

  // The Master switches both on.
  await page.goto("/overseas/agent/team");
  await expect(page.getByText("Student journey only")).toBeVisible();
  await page.getByRole("button", { name: "Permissions for Tau Staff" }).click();
  await page.getByRole("checkbox", { name: "Verify documents" }).check();
  await page.getByRole("checkbox", { name: "View reports" }).check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/-S001 permissions saved\./)).toBeVisible();
  await expect(page.getByText("Can verify documents · Can view reports")).toBeVisible();

  // Next page load: Reports is there, and the staff member can only mark a pending document verified.
  await staff.goto("/overseas/agent/dashboard");
  await expect(staff.getByRole("link", { name: "Reports", exact: true })).toBeVisible();
  await staff.goto("/overseas/agent/documents");
  const card = staff.locator(".card", { hasText: "AGN003 Passport" });
  await card.getByRole("button", { name: "Review" }).click();
  await expect(card.getByLabel("Decision")).toHaveCount(0);
  await card.getByRole("button", { name: "Mark verified" }).click();
  // AGN-009: the Documents page lists Pending by default; a verified document leaves it and the list announces the decision.
  await expect(staff.getByRole("status").filter({ hasText: "AGN003 Passport for" })).toContainText("verified.");
  await expect(card).toHaveCount(0);

  // The Master switches both off; the staff member's next request is refused.
  await page.getByRole("button", { name: "Permissions for Tau Staff" }).click();
  await page.getByRole("checkbox", { name: "Verify documents" }).uncheck();
  await page.getByRole("checkbox", { name: "View reports" }).uncheck();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Student journey only")).toBeVisible();
  await staff.goto("/overseas/agent/reports");
  await expect(staff.getByText("Your agency Master hasn't given you access to reports")).toBeVisible();
  await staffContext.close();
});
