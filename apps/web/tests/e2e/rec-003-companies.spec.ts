import { expect, test, type Page } from "@playwright/test";

// rec-003 (AC1, AC3, AC6, AC7, AC9): the seeded recruiter adds a company (code server-assigned, assigned to them), meets the duplicate
// warning, edits and archives; the seeded placement manager adds an unassigned company and assigns it to the recruiter, with history.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("a recruiter adds, edits and archives a company; a duplicate name warns", async ({ page }) => {
  test.setTimeout(90_000);
  const name = `E2E Rec003 ${Date.now()} Technologies`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.getByRole("link", { name: "Companies" }).first().click();
  await page.waitForURL("**/recruiter/companies");
  await expect(page.getByRole("heading", { name: "Your companies" })).toBeVisible();
  await page.getByRole("link", { name: "Add company" }).first().click();
  await page.waitForURL("**/recruiter/companies/new");

  await page.getByLabel("Company name (required)").fill(name);
  await page.getByLabel("Website").fill("e2e-rec003.example.com");
  await page.getByLabel("City").fill("Pune");
  await page.getByLabel("Lead source").selectOption({ label: "LinkedIn" });
  await page.getByLabel("Priority").selectOption({ label: "Hot" });
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("status").filter({ hasText: /Company CMP-\d{6} created\./ })).toBeVisible();
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByText("Kiran Placement")).toBeVisible();
  await expect(details.getByRole("link", { name: /https:\/\/e2e-rec003\.example\.com/ })).toBeVisible();
  const detailUrl = page.url();

  // D2: the same name in another case is a warning the recruiter must confirm; going back keeps the entry.
  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(name.toUpperCase());
  await page.getByRole("button", { name: "Save company" }).click();
  await expect(page.getByRole("heading", { name: "A similar company already exists" })).toBeVisible();
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(page.getByLabel("Company name (required)")).toHaveValue(name.toUpperCase());

  // Edit, then archive: hidden from the default list, read-only.
  page.once("dialog", (d) => d.accept()); // the leave guard on the unsaved duplicate entry
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("City").fill("Mumbai");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();
  await expect(details.getByText("Mumbai")).toBeVisible();
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Yes, archive" }).click();
  await expect(page.getByText("Company archived.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await page.goto(`/recruiter/companies?q=${encodeURIComponent(name)}`);
  await expect(page.getByText("No companies match these filters.")).toBeVisible();
  await page.getByLabel("Show archived").check();
  await expect(page.getByRole("region", { name: "Companies" }).getByRole("link", { name })).toBeVisible();
});

test("a placement manager adds an unassigned company and assigns it to a recruiter", async ({ page }) => {
  test.setTimeout(90_000);
  const name = `E2E Rec003 Queue ${Date.now()}`;
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.getByRole("link", { name: "Companies" }).first().click();
  await page.waitForURL("**/recruiter/companies");
  await expect(page.getByRole("heading", { name: "Your team's companies" })).toBeVisible();
  await page.getByRole("link", { name: "Add company" }).first().click();
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Not assigned to a recruiter yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0); // a manager reassigns; recruiters edit

  await page.getByRole("combobox", { name: "Assign to" }).fill("Kiran");
  await page.getByRole("option", { name: /Kiran Placement/ }).click();
  await page.getByRole("button", { name: "Assign", exact: true }).click();
  await page.getByRole("button", { name: "Yes, assign" }).click();
  await expect(page.getByText("Assigned to Kiran Placement.")).toBeVisible();
  await expect(page.getByText(/Unassigned → Kiran Placement/)).toBeVisible();

  await page.goto(`/recruiter/companies?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("region", { name: "Companies" }).getByRole("cell", { name: "Kiran Placement" })).toBeVisible();
});

test("the company list fits a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies");
  await expect(page.getByRole("heading", { name: "Your companies" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
