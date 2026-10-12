import { expect, test, type Page } from "@playwright/test";

// mgmt-011 (EVID-017 §9, DEC-SCOPE-193): salary totals per department. The accountant records a month and sees the employee cost, the
// ratio ("—" without revenue) and the automatic "Salaries" ledger line; the super admin is refused (M13). Each run uses its own far-past
// month, since the stack DB is shared and never emptied.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const month = `${2001 + Math.floor(Math.random() * 25)}-${String(1 + Math.floor(Math.random() * 12)).padStart(2, "0")}`;

test("signed out, /management/salaries sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/salaries");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fsalaries$/);
});

test("the accountant records a month's salaries, sees the employee cost and finds the ledger line", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await page.getByRole("link", { name: "Salaries" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Salaries & employee cost" })).toBeVisible();

  await page.getByLabel("Month", { exact: true }).fill(month);
  await page.getByRole("button", { name: "Show month" }).click();
  await expect(page).toHaveURL(new RegExp(`month=${month}`));

  await page.getByLabel("Employees for Training", { exact: true }).fill("4");
  await page.getByLabel("Salary payable for Training", { exact: true }).fill("200000");
  await page.getByLabel("Salary paid for Training", { exact: true }).fill("250000");
  await expect(page.getByText("Paid is more than payable")).toBeVisible();
  await page.getByLabel("Salary paid for Training", { exact: true }).fill("180000");
  await page.getByLabel("Incentives for Training", { exact: true }).fill("15000");
  await page.getByLabel("Employer cost for Training", { exact: true }).fill("20000");
  await page.getByRole("button", { name: /^Save / }).click();
  await expect(page.locator(".form-message[role=status]")).toContainText("saved.");

  const cost = page.getByRole("region", { name: "Employee cost ratio" });
  await expect(cost).toContainText("₹2,15,000.00");
  await expect(cost.getByText("—", { exact: true })).toBeVisible(); // no revenue in a far-past month
  await expect(page.getByRole("list", { name: /^Salary figures for / })).toContainText("4");

  // SM8: the saved row is one automatic "Salaries" expense line in the ledger.
  await page.goto(`/management/ledger?include=auto&month=${month}&kind=expense`);
  await expect(page.getByText("Salaries · Training")).toHaveCount(1);
});

test("the super admin has no entry and is refused the page (M13)", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management");
  await expect(page.getByRole("link", { name: "Salaries" })).toHaveCount(0);
  await page.goto("/management/salaries");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
