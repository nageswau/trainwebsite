import { test, expect, type Page } from "@playwright/test";

// ccrm-021 (DEC-SCOPE-249) -- document status list, passport expiry and versions. Requires the stack with `python -m app.seed` applied;
// creates its own application and document (ovs-005's pattern), never touching the seeded student's documents.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");

async function passportForCounselor(page: Page, documentType: string) {
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;
  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const application = await (await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: universities[0].id, counselor_id: counselorId } })).json();
  await page.request.post("/api/v1/workflows/overseas/documents", { data: { application_id: application.id, document_type: documentType, file_url: "uploads/e2e-passport.pdf" } });
}

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a counselor verifies a passport only with an expiry date, then replaces it with a new version", async ({ page }) => {
  const documentType = `Passport E2E ${Date.now()}`;
  await passportForCounselor(page, documentType);
  await signIn(page, "counselor@edusphere.local", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/documents");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Document Verification" }) }).last();
  const card = panel.locator(".card", { hasText: documentType });
  await expect(card.locator(".badge")).toHaveText("Pending review");

  await card.getByRole("button", { name: "Review" }).click();
  await card.getByLabel("Decision").selectOption("verified");
  await card.getByRole("button", { name: "Submit review" }).click();
  await expect(card.getByText("Add the passport's expiry date before verifying it")).toBeVisible();

  await card.getByLabel("Expiry date (needed to verify a passport)").fill("2034-05-31");
  await card.getByRole("button", { name: "Submit review" }).click();
  await expect(card.getByText(/Document reviewed/)).toBeVisible();
  await expect(card.locator(".badge")).toHaveText("Verified");
  await expect(card).toContainText("Expires 31 May 2034");

  await card.getByRole("button", { name: /^Replace file of/ }).click();
  await card.getByLabel("New file (PDF, JPEG or PNG)").setInputFiles({ name: "new.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByRole("button", { name: "Upload new version" }).click();
  await expect(panel.getByText(/New version uploaded/)).toBeVisible();
  await expect(panel.locator(".card", { hasText: documentType })).toHaveCount(1); // the old version left the queue
  await expect(card.locator(".badge")).toHaveText("Pending review");
  await expect(card).toContainText("Replaces an earlier version");
  await expect(card).toContainText("Expires 31 May 2034"); // kept from the replaced version
});
