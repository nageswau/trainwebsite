import { expect, test, type Page } from "@playwright/test";

// mgmt-004 (EVID-017 §8/§22, spec ML1-ML16): AC1 -- the accountant records Office rent ₹1,20,000 (shared) and submits it, a partner
// approves it, and the month's approved expenses grow by exactly that amount; AC3 -- the super admin is refused. The shared test
// database holds other entries, so the check is the change in the total, scoped to the Office rent category and this month.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const month = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit" }).format(new Date());
const rupees = (text: string) => Number(text.replace(/[^\d.-]/g, ""));

async function officeRentExpenses(page: Page): Promise<number> {
  await page.goto("/management/ledger");
  await page.getByLabel("Month").fill(month);
  await page.getByRole("combobox", { name: "Category" }).selectOption({ label: "Office rent" });
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/category=/);
  const tile = page.getByRole("list", { name: "Approved totals" }).getByRole("listitem").filter({ hasText: "Approved expenses" });
  return rupees((await tile.locator("dd").textContent()) ?? "");
}

test("signed out, /management/ledger sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/ledger");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fledger$/);
});

test("the accountant records rent, a partner approves it, and it counts in the expenses", async ({ browser }) => {
  const description = `Office rent for October e2e-${Date.now()}`;
  const accountant = await (await browser.newContext()).newPage();
  await signIn(accountant, "accountant@edusphere.local");
  await accountant.getByRole("link", { name: "Ledger", exact: true }).first().click();
  await expect(accountant.getByRole("heading", { level: 2, name: "Ledger" })).toBeVisible();
  await accountant.getByRole("link", { name: "New entry" }).click();
  await accountant.getByLabel("Category").selectOption({ label: "Office rent (fixed)" });
  await accountant.getByLabel("Amount (₹)").fill("1,20,000");
  await accountant.getByLabel("Vertical").selectOption({ label: "Shared (company-wide)" });
  await accountant.getByLabel("Description").fill(description);
  await accountant.getByRole("button", { name: "Save and submit" }).click();
  await expect(accountant.getByRole("heading", { level: 2, name: description })).toBeVisible();
  await expect(accountant.locator("dd").filter({ hasText: "Awaiting approval" })).toBeVisible();
  await expect(accountant.getByRole("button", { name: "Approve" })).toHaveCount(0); // AC: an accountant never approves
  const entryUrl = accountant.url();

  const partner = await (await browser.newContext()).newPage();
  await signIn(partner, "partner.one@edusphere.local");
  const before = await officeRentExpenses(partner);
  await partner.getByRole("link", { name: "Awaiting approval" }).click();
  await partner.getByRole("link", { name: description }).click();
  await partner.getByRole("button", { name: "Approve" }).click();
  await expect(partner.getByRole("status")).toHaveText("Entry approved.");
  await expect(partner.locator("dd").filter({ hasText: /^Approved$/ })).toBeVisible();
  expect(await officeRentExpenses(partner)).toBe(before + 120000);

  // The approved entry is locked for the accountant: no Edit, only a reversal.
  await accountant.goto(entryUrl);
  await expect(accountant.getByRole("link", { name: "Edit" })).toHaveCount(0);
  await expect(accountant.getByRole("button", { name: "Reverse" })).toBeVisible();
});

test("the super admin is refused the ledger", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/ledger");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
