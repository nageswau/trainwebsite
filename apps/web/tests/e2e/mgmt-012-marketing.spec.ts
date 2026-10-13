import { expect, test, type Page } from "@playwright/test";

// mgmt-012 (EVID-017 §10, §15, DEC-SCOPE-206): marketing budget & ROI. The accountant opens a month, sees the ROI table per channel and
// the §15 figures, sees a 422 on its channel, saves a budget and sees it in the table; the super admin sees the lead figures with no
// money and no budget form (M13). Each run uses its own far-past month, since the stack DB is shared and never emptied.

async function signIn(page: Page, email: string, landing: string, login = "/admin/login") {
  await page.goto(login);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const month = `${1950 + Math.floor(Math.random() * 50)}-${String(1 + Math.floor(Math.random() * 12)).padStart(2, "0")}`;

test("signed out, /management/marketing sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/marketing");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fmarketing$/);
});

test("the accountant sets a month's budgets and sees them in the ROI table", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await page.getByRole("link", { name: "Marketing budget & ROI", exact: true }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Marketing budget & ROI" })).toBeVisible();
  await expect(page.getByRole("table", { name: /^Marketing ROI by channel, / })).toBeVisible(); // the current month by default

  await page.getByLabel("Month", { exact: true }).fill(month);
  await page.getByRole("button", { name: "Show month" }).click();
  await expect(page).toHaveURL(new RegExp(`month=${month}`));
  const table = page.getByRole("table", { name: /^Marketing ROI by channel, / });
  await expect(table.getByRole("rowheader")).toHaveCount(14); // 13 lead sources + Total
  await expect(page.getByRole("list", { name: /^Marketing figures, / })).toContainText("Not tracked"); // influencer leads

  // A 422 lands on its channel and nothing is saved.
  await page.getByLabel("Instagram budget (₹)").fill("-5");
  await page.getByRole("button", { name: /^Save .* budgets$/ }).click();
  await expect(page.locator("#budget-instagram-error")).toHaveText("An amount can't be negative");
  await expect(page.getByLabel("Instagram budget (₹)")).toHaveAttribute("aria-invalid", "true");

  await page.getByLabel("Instagram budget (₹)").fill("100000");
  await page.getByLabel("Google budget (₹)").fill("0");
  await page.getByRole("button", { name: /^Save .* budgets$/ }).click();
  await expect(page.locator(".form-message[role=status]")).toContainText("saved.");
  await expect(table.getByRole("row", { name: /^Instagram/ })).toContainText("₹1,00,000.00");
  await expect(table.getByRole("row", { name: /^Google/ })).toContainText("₹0.00");
  await expect(table.getByRole("row", { name: /^School/ })).toContainText("Not set");
  await expect(table.getByRole("row", { name: /^Total/ })).toContainText("₹1,00,000.00");
  await expect(page.getByText(/Last saved by /)).toBeVisible();

  // Blanking a channel removes its budget.
  await page.getByLabel("Instagram budget (₹)").fill("");
  await page.getByRole("button", { name: /^Save .* budgets$/ }).click();
  await expect(table.getByRole("row", { name: /^Instagram/ })).toContainText("Not set");
});

test("on a 375px phone the figures fit and the ROI table scrolls inside its card", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "accountant@edusphere.local", "/management");
  await page.goto("/management/marketing");
  const figures = page.getByRole("list", { name: /^Marketing figures, / }).locator("li > strong");
  await expect(figures).toHaveCount(15);
  const lines = await figures.evaluateAll((els) =>
    els.map((el) => { const r = document.createRange(); r.selectNodeContents(el); return `${el.textContent}: ${new Set([...r.getClientRects()].map((c) => Math.round(c.top))).size}`; }));
  expect(lines.filter((l) => !l.endsWith(": 1"))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375); // no page-level sideways scroll
});

test("the super admin sees the lead figures with no money and no budget form (M13)", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management");
  await expect(page.getByRole("link", { name: "Marketing budget & ROI", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Marketing leads", exact: true }).first().click();
  const table = page.getByRole("table", { name: /^Leads by channel, / });
  await expect(table).toBeVisible();
  // Browser QA12-01: the title and lead-in promise only what this role sees.
  await expect(page.getByRole("heading", { level: 2 })).toHaveText("Marketing leads");
  await expect(page.locator(".portal-title p")).not.toContainText(/budget|spend|revenue|ROI/);
  await expect(table.getByRole("columnheader")).toHaveText(["Channel", "Leads", "Qualified", "Customers", "Conversion"]);
  await expect(page.getByRole("list", { name: /^Marketing figures, / })).not.toContainText("₹");
  await expect(page.getByRole("button", { name: /^Save .* budgets$/ })).toHaveCount(0);
  await expect(page.getByText(/partners and the accountant only/)).toBeVisible();
});

test("a role outside management is refused the page", async ({ page }) => {
  await signIn(page, "itadmin@edusphere.local", "/it/admin/dashboard", "/it/login");
  await page.goto("/management/marketing");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
