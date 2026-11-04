import { expect, test, type Page } from "@playwright/test";

// hrc-006 (DEC-SCOPE-384, AC1/AC3/AC5): the seeded recruiter adds the seeded Placement Officer as the placement-officer owner of a new
// requirement; the officer opens it from their own menu, edits it, sees the owners read-only and no candidate sections; the ownership
// history lists the primary and the officer. Then the recruiter removes the officer, who no longer finds it.

const RECRUITER = "placement@edusphere.local";
const OFFICER = "placement.officer@edusphere.local";
const OFFICER_NAME = "Rohan Placement Officer";

async function signIn(page: Page, email: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a placement officer co-owns a requirement, edits it, and loses it when removed", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const title = `Co-owned Analyst ${stamp}`;
  await signIn(page, RECRUITER, "/recruiter/dashboard");

  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(`E2E Hrc006 ${stamp} Labs`);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  await page.getByRole("region", { name: "Job requirements" }).getByRole("link", { name: "Add job requirement" }).click();
  await page.waitForURL(/\/recruiter\/requirements\/new\?company_id=/);
  await page.getByLabel("Job title (required)").fill(title);
  await page.getByLabel("City", { exact: true }).fill("Pune");
  await page.getByRole("button", { name: "Save requirement" }).click();
  await page.waitForURL(/\/recruiter\/requirements\/[0-9a-f-]{36}$/);
  const requirementUrl = new URL(page.url()).pathname;

  // the primary adds the officer as the placement-officer owner
  const owners = page.getByRole("region", { name: "Owners", exact: true });
  await expect(owners.getByText("Primary owner")).toBeVisible();
  await owners.getByLabel("Owner role").selectOption("placement_officer");
  await owners.getByRole("combobox", { name: "Person" }).fill("Rohan");
  await page.getByRole("option", { name: new RegExp(OFFICER_NAME) }).click();
  await owners.getByRole("button", { name: "Add owner" }).click();
  await expect(page.getByText(`${OFFICER_NAME} added as Placement officer owner.`)).toBeVisible();
  await expect(owners.getByRole("listitem").filter({ hasText: OFFICER_NAME })).toContainText("Placement officer owner");
  const history = page.getByRole("region", { name: "Ownership history" });
  await expect(history.getByText(new RegExp(`added ${OFFICER_NAME} as Placement officer owner`))).toBeVisible();
  await expect(history.getByText(/Kiran Placement added themselves as Primary owner/)).toBeVisible();

  // the officer finds it from their own menu and edits it
  await signIn(page, OFFICER, "/it/placement-officer/dashboard");
  await page.getByRole("link", { name: "Job requirements" }).first().click();
  await page.waitForURL("**/recruiter/requirements");
  await page.getByRole("link", { name: title }).click();
  await page.waitForURL(`**${requirementUrl}`);
  await expect(page.getByRole("region", { name: "Owners", exact: true }).getByRole("button", { name: /Remove|Add owner/ })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Candidates" })).toHaveCount(0);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Department").fill("Analytics");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Details" }).getByText("Analytics")).toBeVisible();

  // the recruiter removes the officer; the officer then gets "not found"
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto(requirementUrl);
  await page.getByRole("region", { name: "Owners", exact: true }).getByRole("button", { name: `Remove ${OFFICER_NAME}` }).click();
  await page.getByRole("button", { name: "Yes, remove" }).click();
  await expect(page.getByText(`${OFFICER_NAME} removed from the owners.`)).toBeVisible();
  await signIn(page, OFFICER, "/it/placement-officer/dashboard");
  await page.goto(requirementUrl);
  await expect(page.getByRole("heading", { name: "Job requirement not found" })).toBeVisible();
});

test("the owners card fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/requirements");
  await page.getByRole("table").getByRole("link").first().click();
  await page.waitForURL(/\/recruiter\/requirements\/[0-9a-f-]{36}$/);
  const owners = page.getByRole("region", { name: "Owners", exact: true });
  await expect(owners).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
