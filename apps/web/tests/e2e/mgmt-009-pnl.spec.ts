import { expect, test, type Page } from "@playwright/test";

// mgmt-009 (spec PL1-PL12): a partner opens the company P&L from the Command Center, sees one row per vertical, the unallocated shared
// row and a total that is the rows' sum, and a chosen quarter survives a reload; the accountant is told university commission is left
// out; the super admin is refused. The shared test database holds many lines, so the checks look at the table's shape and its own sums.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const rupees = (text: string) => Number(text.replace(/[^\d.-]/g, ""));
const TABLE = "Profit and loss by business vertical";

test("a partner reads the P&L, its total adds up, and a chosen quarter survives a reload", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Profit & loss" }).first().click();
  await expect(page).toHaveURL(/\/management\/pnl$/);
  await expect(page.getByRole("heading", { name: "Profit & loss" })).toBeVisible();

  const table = page.getByRole("table", { name: TABLE });
  await expect(table.getByRole("rowheader")).toHaveText(["Abroad Education", "IT Training", "Recruitment", "School projects", "Other", "Shared (company-wide, not allocated)", "Total"]);
  // AC: the total row = the sum of the rows; contribution = revenue - expenses.
  for (const column of [2, 3, 4]) {
    const cells = await table.locator(`tbody tr td:nth-child(${column})`).allTextContents();
    const total = await table.locator(`tfoot tr td:nth-child(${column})`).textContent();
    expect(Math.abs(cells.map(rupees).reduce((a, b) => a + b, 0) - rupees(total ?? ""))).toBeLessThan(0.01);
  }
  for (const row of await table.locator("tbody tr, tfoot tr").all()) {
    const [revenue, expenses, contribution] = (await row.locator("td").allTextContents()).map(rupees);
    expect(Math.abs(revenue - expenses - contribution)).toBeLessThan(0.01);
  }
  await expect(page.getByText(/University commission is not included/)).toHaveCount(0);

  await page.getByLabel("Month", { exact: true }).fill("2025-05");
  await page.getByLabel("Show").selectOption("quarter");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/month=2025-05&period=quarter/);
  await expect(page.getByText(/Q1 \(April–June\) of 2025-26 to date/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Month", { exact: true })).toHaveValue("2025-05");
  await expect(page.getByLabel("Show")).toHaveValue("quarter");
});

test("the accountant reads the P&L without university commission", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/pnl?period=year");
  await expect(page.getByRole("table", { name: TABLE })).toBeVisible();
  await expect(page.getByText("University commission is not included: only partners see it.")).toBeVisible();
});

test("a future month shows the API's message and keeps the form", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/pnl?month=2999-01");
  await expect(page.locator(".form-error")).toHaveText("Choose this month or an earlier one");
  await expect(page.getByRole("form", { name: "Choose a period" })).toBeVisible();
});

test("the super admin is refused the P&L", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/pnl");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
