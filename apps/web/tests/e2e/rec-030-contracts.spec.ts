import { expect, test, type Page } from "@playwright/test";

// rec-030 (AC1, AC3, CT8, CT9, CT10): the seeded recruiter starts a contract at Proposal Sent on a new company; Signed is refused until
// the contract document is uploaded (AC3), then accepted; the company's Contract status follows; an overlapping renewal is refused on the
// form; the seeded placement manager reads it without any write control. AC2 (Expired after the end date) is covered by
// test_rec_030_contracts.py and the component tests.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

test("contract on a company: Proposal Sent, Signed needs the PDF, Contract status, overlap refused; the manager reads only", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(`E2E Rec030 ${Date.now()} Technologies`);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();

  const section = page.getByRole("region", { name: "Contract / MoU" });
  await expect(section.getByText("No contract yet.")).toBeVisible();
  await expect(page.locator("dd", { hasText: "No contract yet" })).toBeVisible(); // CT10 Details row

  // Negative scenario first: end before start is refused on its field.
  await section.getByRole("button", { name: "Start contract" }).click();
  const form = section.getByRole("form", { name: "Start contract" });
  await form.getByLabel("Status").selectOption({ label: "Proposal Sent" });
  await form.getByLabel("Contract start date").fill("2026-05-01");
  await form.getByLabel("Contract end date").fill("2026-04-01");
  await form.getByRole("button", { name: "Start contract" }).click();
  await expect(form.getByText("The end date can't be before the start date")).toBeVisible();
  await form.getByLabel("Contract end date").fill("2027-04-30");
  await form.getByLabel("Fee basis").selectOption("fixed");
  await form.getByLabel("Recruitment fee (₹)").fill("50000");
  await form.getByRole("button", { name: "Start contract" }).click();
  await expect(page.getByRole("status").first()).toHaveText("Contract started.");
  await expect(section.getByText("₹50,000 per hire")).toBeVisible();
  await expect(page.locator("dd", { hasText: "Proposal Sent" })).toBeVisible();

  // AC3: Signed needs the contract document.
  await section.getByRole("button", { name: "Edit contract" }).click();
  let edit = section.getByRole("form", { name: "Edit contract" });
  await edit.getByLabel("Status").selectOption({ label: "Signed" });
  await edit.getByRole("button", { name: "Save contract" }).click();
  await expect(edit.getByText("Upload the signed contract document first")).toBeVisible();
  await edit.getByRole("button", { name: "Cancel" }).click();
  await section.getByLabel(/Upload contract document/).setInputFiles({ name: "signed.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(section.getByRole("link", { name: "Download contract document (PDF)" })).toBeVisible();
  await section.getByRole("button", { name: "Edit contract" }).click();
  edit = section.getByRole("form", { name: "Edit contract" });
  await edit.getByLabel("Status").selectOption({ label: "Signed" });
  await edit.getByRole("button", { name: "Save contract" }).click();
  await expect(section.locator(".badge").first()).toHaveText("Signed");
  await expect(section.getByRole("list", { name: "Contract statuses" }).locator("[aria-current=step]")).toContainText("Signed");
  await expect(page.locator("dd", { hasText: /^Signed$/ })).toBeVisible();

  // CT8: a renewal overlapping the signed contract is refused on the form.
  await section.getByRole("button", { name: "Start renewal" }).click();
  const renewal = section.getByRole("form", { name: "Start contract" });
  await renewal.getByLabel("Contract start date").fill("2027-01-01");
  await renewal.getByRole("button", { name: "Start contract" }).click();
  await expect(renewal.getByRole("alert")).toHaveText("These dates overlap a previous contract of this company");
  await renewal.getByRole("button", { name: "Cancel" }).click();

  // CT9: the manager reads the contract and its document, with no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(detailUrl);
  await expect(section.locator(".badge").first()).toHaveText("Signed");
  await expect(section.getByRole("link", { name: "Download contract document (PDF)" })).toBeVisible();
  await expect(section.getByRole("button", { name: /Edit contract|Start renewal/ })).toHaveCount(0);
  await expect(section.locator("input[type=file]")).toHaveCount(0);
});
