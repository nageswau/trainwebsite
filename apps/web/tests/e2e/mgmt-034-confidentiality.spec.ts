import { expect, test, type Page } from "@playwright/test";

// mgmt-034 (DEC-SCOPE-221, RBAC §2.146): the confidentiality sweep in the browser. University commission is the partners' (M3, CS1): the
// accountant's accounts dashboard and ledger leave it out and say so, while a partner still sees it. Each tier is refused the pages above
// it (M2/M13): the accountant gets no partner-only page, the super admin no finance page.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const NOT_INCLUDED = "University commission is not included: only partners see it.";

test("the accountant's accounts and ledger leave university commission out and say so", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await page.goto("/management/accounts");
  const sources = page.getByRole("list", { name: "Receivables by source" });
  await expect(sources.getByRole("listitem")).toHaveText([/^Student fees: /, /^Recruitment invoices: /]);
  await expect(page.getByText(NOT_INCLUDED)).toBeVisible();

  await page.goto("/management/ledger?include=auto");
  await expect(page.getByText(/Automatic lines \(/)).toContainText("approved BDM trip expenses and recruiter receipts)");
  await expect(page.getByText(/Automatic lines \(/)).toContainText(NOT_INCLUDED);
  await expect(page.getByRole("table").getByText("University commission", { exact: true })).toHaveCount(0);
});

test("a partner sees university commission on the accounts dashboard", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.goto("/management/accounts");
  await expect(page.getByRole("list", { name: "Receivables by source" }).getByRole("listitem")).toHaveCount(3);
  await expect(page.getByRole("list", { name: "Receivables by source" })).toContainText("University commission: ₹");
  await expect(page.getByText(NOT_INCLUDED)).toHaveCount(0);
});

for (const [who, email, landing, pages, detail] of [
  ["accountant", "accountant@edusphere.local", "/management", ["investments", "capital", "reviews"], "Only partners can open this"],
  ["super admin", "superadmin@edusphere.local", "/admin", ["accounts", "ledger", "salaries"], "Finance access required"],
] as const) {
  test(`the ${who} is refused the pages above their tier`, async ({ page }) => {
    await signIn(page, email, landing);
    for (const path of pages) {
      await page.goto(`/management/${path}`);
      await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
      await expect(page.getByText(detail)).toBeVisible();
    }
  });
}
