import { expect, test, type Page } from "@playwright/test";

// hrc-005 (DEC-SCOPE-381, AC1-AC5): the seeded recruiter adds a requirement with the §4.2 fields (the location comes from the city,
// state and country), sees them and "Last updated" on the detail page; a second one with the same title and city is flagged as a
// possible duplicate, and is saved only with a reason, which the change history records.

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
}

const RECRUITER = "placement@edusphere.local";

test("a recruiter records the vacancy fields and is warned about a duplicate", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const company = `E2E Hrc005 ${stamp} Labs`;
  const title = `Data Engineer ${stamp}`;
  await signIn(page, RECRUITER);

  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(company);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const companyUrl = page.url();
  await page.getByRole("region", { name: "Job requirements" }).getByRole("link", { name: "Add job requirement" }).click();
  await page.waitForURL(/\/recruiter\/requirements\/new\?company_id=/);

  await page.getByLabel("Requisition reference").fill(`RQ-${stamp}`);
  await page.getByLabel("Job title (required)").fill(title);
  await page.getByLabel("Certifications").fill("AWS SAA");
  await page.getByLabel("Country").fill("India");
  await page.getByLabel("State", { exact: true }).fill("Maharashtra");
  await page.getByLabel("City", { exact: true }).fill("Pune");
  await page.getByLabel("Relocation required").selectOption({ label: "Yes" });
  await page.getByLabel("Travel").fill("Up to 25%");
  await page.getByLabel("Salary from", { exact: true }).fill("1000");
  await page.getByLabel("Salary to", { exact: true }).fill("2000");
  await page.getByLabel("Salary currency").fill("usd");
  await page.getByLabel("Pay period").selectOption({ label: "A month" });
  await page.getByLabel("Benefits").fill("Health cover");
  await page.getByLabel("Expected joining date").fill("2027-01-15");
  await page.getByRole("button", { name: "Save requirement" }).click();

  await page.waitForURL(/\/recruiter\/requirements\/[0-9a-f-]{36}$/);
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByText(`RQ-${stamp}`)).toBeVisible();
  await expect(details.getByText("Pune, Maharashtra, India").first()).toBeVisible(); // the derived location
  await expect(details.getByText("USD 1,000 – USD 2,000 a month")).toBeVisible();
  await expect(details.getByText("Up to 25%")).toBeVisible();
  await expect(details.getByText(/on .*\d{4}/).last()).toBeVisible(); // Last updated: who and when

  // a second one: same title and city
  await page.goto(companyUrl);
  await page.getByRole("region", { name: "Job requirements" }).getByRole("link", { name: "Add job requirement" }).click();
  await page.waitForURL(/\/recruiter\/requirements\/new\?company_id=/);
  await page.getByLabel("Job title (required)").fill(title.toUpperCase());
  await page.getByLabel("City", { exact: true }).fill("pune");
  await page.getByRole("button", { name: "Save requirement" }).click();
  const panel = page.getByRole("region", { name: "Possible duplicate" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("link", { name: /REQ-\d{6}/ })).toBeVisible();
  await panel.getByRole("button", { name: "Save anyway" }).click();
  await expect(panel.getByText("Give a reason to save anyway")).toBeVisible();
  await panel.getByLabel(/Why is this not a duplicate/).fill("Second batch for a new client team");
  await panel.getByRole("button", { name: "Save anyway" }).click();

  await page.waitForURL(/\/recruiter\/requirements\/[0-9a-f-]{36}$/);
  const history = page.getByRole("list", { name: "Change history" });
  await expect(history.getByText("Saved despite a possible duplicate")).toBeVisible();
});
