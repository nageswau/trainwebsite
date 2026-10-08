import { expect, test, type Page } from "@playwright/test";

// rec-007 (AC1, AC2, AC5, AC7): the seeded recruiter adds a company, then "+ Add Job Requirement" from it with §6 fields and skills
// (an unmatched one is flagged); a bad experience range is caught; the status moves New -> Requirement Received with a note and the
// history shows it; the requirement is in the list and on the company page.

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
}

const RECRUITER = "placement@edusphere.local";

test("a recruiter adds a job requirement from a company and moves its status", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const company = `E2E Rec007 ${stamp} Labs`;
  const title = `Python Developer ${stamp}`;
  await signIn(page, RECRUITER);

  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(company);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const section = page.getByRole("region", { name: "Job requirements" });
  await expect(section.getByText("No job requirements for this company yet.")).toBeVisible();
  await section.getByRole("link", { name: "Add job requirement" }).click();
  await page.waitForURL(/\/recruiter\/requirements\/new\?company_id=/);
  await expect(page.getByText(company)).toBeVisible();

  await page.getByLabel("Job title (required)").fill(title);
  await page.getByLabel("Job location (required)").fill("Hyderabad");
  await page.getByLabel("Number of vacancies").fill("3");
  await page.getByLabel("Experience from (years)").fill("2");
  await page.getByLabel("Experience to (years)").fill("1");
  await page.getByLabel("Work mode").selectOption({ label: "Hybrid" });
  await page.getByLabel("Priority").selectOption({ label: "High" });
  await page.getByLabel("Required skills").fill("Python, SQL, Rec007Skill" + stamp);
  await page.getByRole("button", { name: "Save requirement" }).click();
  await expect(page.getByText("Must be at least the minimum experience")).toBeVisible(); // caught before the round trip
  await page.getByLabel("Experience to (years)").fill("4");
  await page.getByRole("button", { name: "Save requirement" }).click();

  await page.waitForURL(/\/recruiter\/requirements\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("status").filter({ hasText: /Requirement REQ-\d{6} created\./ })).toBeVisible();
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByText("2–4 years")).toBeVisible();
  await expect(details.getByText("Hybrid", { exact: true })).toBeVisible();
  await expect(details.getByText("Not in Skills Master")).toHaveCount(1); // the made-up skill is kept and flagged
  await expect(page.getByRole("heading", { name: new RegExp(title) }).getByText("New", { exact: true })).toBeVisible();

  const change = page.getByRole("region", { name: "Change status" });
  await expect(change.getByLabel("New status").locator("option")).toHaveText(["Choose a status", "Requirement Received", "On Hold", "Closed", "Cancelled"]);
  await change.getByLabel("New status").selectOption({ label: "Requirement Received" });
  await change.getByLabel("Note (optional)").fill("Call with HR");
  await change.getByRole("button", { name: "Change status" }).click();
  await expect(page.getByText("Status changed to Requirement Received.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Status history" }).getByText(/New → Requirement Received — Call with HR/)).toBeVisible();

  await page.goto(`/recruiter/requirements?q=${encodeURIComponent(title)}`);
  const row = page.getByRole("row", { name: new RegExp(title) });
  await expect(row.getByText("Requirement Received")).toBeVisible();
  await expect(row.getByText(company)).toBeVisible();
});
