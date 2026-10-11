import { expect, test, type Page } from "@playwright/test";

// rec-031 (AC1, AC2, RV6-RV10): the seeded recruiter records a ₹1,50,000 invoice on a new requirement, an over-payment is refused on its
// field (AC2), ₹1,00,000 is received and ₹50,000 is outstanding (AC1); the invoice is on the Receivables list and the company's Revenue
// section; the seeded manager sets the requirement's fee. AC3 (Joined only) and the percentage-of-CTC pricing are covered by
// test_rec_031_revenue.py, which builds joined hires directly.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const today = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

test("invoice, over-payment refused, part payment -> outstanding; receivables and company; the manager sets the fee", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const stamp = Date.now();
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec031 ${stamp} Pvt` } });
  expect(company.status()).toBe(201);
  const companyId = (await company.json()).company.id as string;
  const requirement = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: companyId, title: `E2E Revenue ${stamp}`, location: "Pune" } });
  expect(requirement.status()).toBe(201);
  const requirementId = (await requirement.json()).requirement.id as string;
  const number = `E2E-INV-${stamp}`;

  await page.goto(`/recruiter/requirements/${requirementId}`);
  const section = page.getByRole("region", { name: "Revenue" });
  await expect(section.getByText("No invoices yet.")).toBeVisible();
  await expect(section.locator("dd", { hasText: "No fee set" }).first()).toBeVisible();

  await section.getByRole("button", { name: "Add invoice" }).click();
  const form = section.getByRole("form", { name: "Add invoice" });
  await form.getByLabel("Invoice number").fill(number);
  await form.getByLabel("Invoice date").fill(today());
  await form.getByLabel("Payment due").fill(today());
  await form.getByLabel("Amount (₹)").fill("-5000");
  await form.getByRole("button", { name: "Save invoice" }).click();
  await expect(form.getByText("The amount must be more than ₹0")).toBeVisible(); // negative scenario
  await form.getByLabel("Amount (₹)").fill("150000");
  await form.getByRole("button", { name: "Save invoice" }).click();
  await expect(section.getByText("Invoice saved.")).toBeVisible();

  await section.getByRole("button", { name: `Record payment for ${number}` }).click();
  const pay = section.getByRole("form", { name: `Record payment for ${number}` });
  await pay.getByLabel("Received date").fill(today());
  await pay.getByLabel("Amount (₹)").fill("150000.01");
  await pay.getByRole("button", { name: "Save payment" }).click();
  await expect(pay.getByText("This payment is more than the ₹1,50,000.00 outstanding")).toBeVisible(); // AC2
  await pay.getByLabel("Amount (₹)").fill("100000");
  await pay.getByRole("button", { name: "Save payment" }).click();
  await expect(section.getByText("Payment saved.")).toBeVisible();
  await expect(section.locator("dt", { hasText: "Outstanding amount" }).locator("+ dd")).toHaveText("₹50,000.00"); // AC1
  await expect(section.getByText("Part paid")).toBeVisible();

  await page.goto(`/recruiter/receivables?company_id=${companyId}`);
  await expect(page.getByRole("list", { name: "Invoices" }).getByText(number)).toBeVisible();
  await expect(page.getByText("Outstanding in total: ₹50,000.00")).toBeVisible();

  await page.goto(`/recruiter/companies/${companyId}`);
  const companyRevenue = page.getByRole("region", { name: "Revenue" });
  await expect(companyRevenue.locator("dt", { hasText: "Outstanding amount" }).locator("+ dd")).toHaveText("₹50,000.00");
  await expect(companyRevenue.getByRole("button", { name: "Set fee for this requirement" })).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const managerSection = page.getByRole("region", { name: "Revenue" });
  await managerSection.getByRole("button", { name: "Set fee for this requirement" }).click();
  const fee = managerSection.getByRole("form", { name: "Fee for this requirement" });
  await fee.getByLabel(/^Fee basis/).selectOption("fixed");
  await fee.getByLabel(/^Fee per hire/).fill("50000");
  await fee.getByRole("button", { name: "Save fee" }).click();
  await expect(managerSection.getByText("₹50,000 per hire · set for this requirement")).toBeVisible();
  await expect(managerSection.getByText(/Invoiced more than the expected revenue/)).toBeVisible(); // RV9: no one has joined yet
});
