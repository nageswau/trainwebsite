import { expect, test, type Page } from "@playwright/test";

// mgmt-010 (spec ME1-ME10): the accountant opens the expense dashboard from the Command Center, sees the eight §8 heads, the total and
// the month-by-month table, and a chosen month survives a reload; the super admin is refused. The shared test database holds many
// lines, so the checks look at the table's shape and its own sums, not exact figures.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const rupees = (text: string) => Number(text.replace(/[^\d.-]/g, ""));

test("the accountant reads the expense dashboard and picks an earlier month", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Expenses & rent" }).first().click();
  await expect(page).toHaveURL(/\/management\/expenses$/);
  await expect(page.getByRole("heading", { name: "Expense dashboard" })).toBeVisible();

  const heads = page.getByRole("table", { name: "Expenses by head" });
  await expect(heads.getByRole("rowheader")).toHaveText(["Rent", "Salaries", "Marketing", "Travel", "Trainers", "Commissions", "Technology", "Other", "Total"]);
  // AC: the total = the sum of the heads (annual column).
  const annual = await heads.locator("tbody tr td:nth-child(3)").allTextContents();
  const total = await heads.locator("tfoot tr td:nth-child(3)").textContent();
  expect(Math.abs(annual.map(rupees).reduce((a, b) => a + b, 0) - rupees(total ?? ""))).toBeLessThan(0.01);
  // AC: annual = the sum of the months.
  const months = page.getByRole("table", { name: "Month by month" });
  const monthly = await months.locator("tbody tr td").allTextContents();
  expect(Math.abs(monthly.map(rupees).reduce((a, b) => a + b, 0) - rupees(total ?? ""))).toBeLessThan(0.01);

  await page.getByLabel("Month", { exact: true }).fill("2025-04");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/month=2025-04/);
  await expect(page.getByText(/Monthly: April 2025\. Annual: the financial year 2025-26/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Month", { exact: true })).toHaveValue("2025-04");
  await expect(page.getByRole("table", { name: "Month by month" }).locator("tbody tr")).toHaveCount(1);
  await expect(page.getByRole("link", { name: /expense lines in the ledger/ })).toHaveAttribute("href", "/management/ledger?month=2025-04&kind=expense&include=auto");
});

test("the super admin is refused the expense dashboard", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/expenses");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
