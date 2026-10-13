import { expect, test, type Page } from "@playwright/test";

// mgmt-013 (EVID-017 §22, DEC-SCOPE-196): the accounts dashboard. The accountant opens a month, sees its income and expense heads and the
// financial position ("Not entered" until the month-end balances are typed), saves the balances and sees a 422 on its field; the super
// admin is refused (M13). Each run uses its own far-past month, since the stack DB is shared and never emptied.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const month = `${1950 + Math.floor(Math.random() * 50)}-${String(1 + Math.floor(Math.random() * 12)).padStart(2, "0")}`;

test("signed out, /management/accounts sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/accounts");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Faccounts$/);
});

test("the accountant opens a month, enters its balances and sees them in the financial position", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await page.getByRole("link", { name: "Accounts", exact: true }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Accounts" })).toBeVisible();
  await expect(page.getByRole("table", { name: /^Income by head, / })).toBeVisible(); // the current month by default

  await page.getByLabel("Month", { exact: true }).fill(month);
  await page.getByRole("button", { name: "Show month" }).click();
  await expect(page).toHaveURL(new RegExp(`month=${month}`));
  const position = page.getByRole("list", { name: "Financial position" });
  const income = page.getByRole("table", { name: /^Income by head, / });
  await expect(income.getByRole("rowheader")).toHaveText(["Abroad education", "IT training", "Recruitment", "School projects", "Other", "Total income"]);
  await expect(page.getByRole("table", { name: /^Expenses by head, / }).getByRole("rowheader")).toHaveCount(9);

  // A 422 lands on its field and nothing is saved.
  await page.getByLabel("Payables (₹)").fill("-5");
  await page.getByRole("button", { name: /^Save .* balances$/ }).click();
  await expect(page.locator("#balance-payables-error")).toHaveText("An amount can't be negative");
  await expect(page.getByLabel("Payables (₹)")).toHaveAttribute("aria-invalid", "true");

  await page.getByLabel("Cash/bank (₹)").fill("-2500.50");
  await page.getByLabel("Payables (₹)").fill("18000");
  await page.getByRole("button", { name: /^Save .* balances$/ }).click();
  await expect(page.locator(".form-message[role=status]")).toContainText("saved.");
  await expect(position).toContainText("-₹2,500.50");
  await expect(position).toContainText("₹18,000.00");
  await expect(position.locator("li", { hasText: "Tax liabilities" })).toContainText("Not entered");
  await expect(page.getByText(/Last saved by /)).toBeVisible();
});

// Browser QA-P1/P2: on a phone each position figure stays on one line, and every head's amount is in view without scrolling the table.
for (const width of [360, 375]) {
  test(`on a ${width}px phone the figures fit and the amounts are in view`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await signIn(page, "accountant@edusphere.local", "/management");
    await page.goto("/management/accounts");
    const figures = page.getByRole("list", { name: "Financial position" }).locator("li > strong");
    await expect(figures).toHaveCount(6);
    const lines = await figures.evaluateAll((els) =>
      els.map((el) => { const r = document.createRange(); r.selectNodeContents(el); return `${el.textContent}: ${new Set([...r.getClientRects()].map((c) => Math.round(c.top))).size}`; }));
    expect(lines.filter((l) => !l.endsWith(": 1"))).toEqual([]);
    for (const name of [/^Income by head, /, /^Expenses by head, /]) {
      const rights = await page.getByRole("table", { name }).locator("tbody td:nth-child(2)").evaluateAll((els) =>
        els.map((el) => Math.round(el.getBoundingClientRect().right)));
      expect(rights.filter((x) => x > width)).toEqual([]);
    }
  });
}

test("the super admin has no entry and is refused the page (M13)", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management");
  await expect(page.getByRole("link", { name: "Accounts", exact: true })).toHaveCount(0);
  await page.goto("/management/accounts");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
