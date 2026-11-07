import { expect, test, type Page } from "@playwright/test";

// pob-010 (DEC-SCOPE-420): a recruiter adds a vendor, submits its form and NDA; a super admin approves; the recruiter signs the vendor agreement and activates it (AC1).
// The vendor is on the vendor list and never on the client list or the requirement picker's source (AC2); no sideways scroll on a phone.
const ADMIN = "superadmin@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const PDF = { name: "file.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n") };
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(email === ADMIN ? "/admin/login" : "/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function uploadDocument(page: Page, kind: string) {
  const form = page.locator("form", { has: page.getByLabel("Document type") });
  await form.getByLabel("Document type").selectOption(kind);
  await form.locator("input[type=file]").setInputFiles(PDF);
  await form.getByRole("button", { name: /upload/i }).click();
  await expect(page.getByText("Document uploaded.")).toBeVisible();
}

test("a vendor is added, onboarded and contracted, and stays off the client list", async ({ page }) => {
  test.setTimeout(150_000);
  const name = `POB10 Vendor ${Date.now()} Pvt`;
  await signIn(page, RECRUITER);
  await page.goto("/recruiter/vendors");
  await page.getByRole("link", { name: "Add vendor" }).first().click();
  await page.waitForURL("**/recruiter/companies/new?vendor=1");
  await expect(page.getByLabel("Relationship")).toHaveValue("vendor");
  await page.getByLabel("Company name").fill(name);
  await page.getByRole("button", { name: /save|add company|create/i }).first().click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}/);
  const detail = page.url().split("?")[0];

  const card = page.locator("section", { has: page.getByRole("heading", { name: "Vendor onboarding" }) });
  await expect(card.getByText("Prospect", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Stage history" })).toHaveCount(0);

  // The form first: the server's refusal shows on the card.
  await card.getByRole("button", { name: "Move to Registration submitted" }).click();
  await expect(card.getByRole("alert")).toHaveText("Upload the vendor onboarding form first");
  await uploadDocument(page, "vendor_onboarding_form");
  await expect(card.getByText("On file", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Move to Registration submitted" }).click();
  await expect(page.getByText("Vendor moved to Registration submitted.").first()).toBeVisible();
  await uploadDocument(page, "nda");

  // Approval is a manager's or super admin's: the recruiter is not offered it.
  await expect(card.getByRole("button", { name: "Move to Approved" })).toHaveCount(0);
  await signIn(page, ADMIN);
  await page.goto(detail);
  await card.getByRole("button", { name: "Move to Approved" }).click();
  await expect(page.getByText("Vendor moved to Approved.").first()).toBeVisible();

  await signIn(page, RECRUITER);
  await page.goto(detail);
  const agreement = page.locator("#company-vendor-agreement");
  await agreement.getByRole("button", { name: "Start agreement" }).click();
  await agreement.getByLabel("Who pays whom").selectOption("we_pay_vendor");
  await agreement.getByLabel("Confidentiality terms").fill("Two years");
  await agreement.getByRole("button", { name: "Start agreement" }).click();
  await expect(agreement.getByText("We pay the vendor")).toBeVisible();
  await agreement.locator("input[type=file]").first().setInputFiles(PDF);
  await expect(agreement.getByText("Contract document saved.").or(page.getByText("Contract document saved.")).first()).toBeVisible();
  await agreement.getByRole("button", { name: "Edit agreement" }).click();
  await agreement.getByLabel("Status").selectOption("signed");
  await agreement.getByRole("button", { name: "Save agreement" }).click();
  await expect(page.getByText("Agreement saved.").first()).toBeVisible();
  await card.getByRole("button", { name: "Move to Active" }).click();
  await expect(page.getByText("Vendor moved to Active.").first()).toBeVisible();

  // AC2: on the vendor list, never on the client list.
  await page.goto(`/recruiter/vendors?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Active", exact: true })).toBeVisible();
  await page.goto(`/recruiter/companies?q=${encodeURIComponent(name)}`);
  await expect(page.getByText("No companies match these filters.")).toBeVisible();
});

test("the vendor list fits a phone and filters by onboarding status", async ({ page }) => {
  await signIn(page, RECRUITER);
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/recruiter/vendors?vendor_status=suspended");
  await expect(page.getByLabel("Onboarding")).toHaveValue("suspended");
  await expect(page.getByRole("heading", { name: "Vendors", exact: true })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
