import { test, expect } from "@playwright/test";

// OVS-005 -- Document upload against checklist. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied. Creates its own
// throwaway document (via the real API, pre-assigned to the seeded counselor) instead
// of touching the seeded student's own on-record documents -- same "create your own
// record, never touch shared seed data" principle used throughout this project.

async function createDocumentAssignedToCounselor(page: import("@playwright/test").Page, documentType: string) {
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const alreadyApplied = ((await (await page.request.get("/api/v1/portal/overseas/student/applications")).json()).rows || []) as { university: string }[];
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const target = universities.find((u) => !alreadyApplied.some((a) => a.university === u.name));
  if (!target) throw new Error("No unapplied university available to pick in this seed dataset");
  const application = await (await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: target.id, counselor_id: counselorId } })).json();

  const document = await (
    await page.request.post("/api/v1/workflows/overseas/documents", { data: { application_id: application.id, document_type: documentType, file_url: "uploads/e2e-test-document.pdf" } })
  ).json();
  return { documentId: document.id as string };
}

test("student can download their own uploaded document (OVS-005-AC01)", async ({ page }) => {
  const documentType = `E2E Passport ${Date.now()}`;
  await createDocumentAssignedToCounselor(page, documentType);

  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");

  await page.goto("/overseas/student/documents");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Your Documents" }) }).locator(".card", { hasText: documentType });
  await expect(card).toBeVisible();
  const [popup] = await Promise.all([page.waitForEvent("popup"), card.getByRole("button", { name: "Download" }).click()]);
  expect(popup.url()).not.toBe("about:blank");
});

test("assigned counselor can view and verify the document (OVS-005-AC01)", async ({ page }) => {
  const documentType = `E2E Transcript ${Date.now()}`;
  await createDocumentAssignedToCounselor(page, documentType);

  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");

  await page.goto("/overseas/counselor/documents");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Document Verification" }) }).locator(".card", { hasText: documentType });
  await expect(card).toBeVisible();

  const [popup] = await Promise.all([page.waitForEvent("popup"), card.getByRole("button", { name: "View document" }).click()]);
  expect(popup.url()).not.toBe("about:blank");

  await card.getByRole("button", { name: "Review" }).click();
  await card.getByLabel("Decision").selectOption("verified");
  await card.getByLabel("Reviewer notes").fill("Looks good.");
  await card.getByRole("button", { name: "Submit review" }).click();
  await expect(card.getByText(/Document reviewed/)).toBeVisible();
});

test("the document workspaces require authentication", async ({ page }) => {
  await page.goto("/overseas/student/documents");
  await expect(page).toHaveURL(/\/overseas\/login/);
  await page.goto("/overseas/counselor/documents");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
