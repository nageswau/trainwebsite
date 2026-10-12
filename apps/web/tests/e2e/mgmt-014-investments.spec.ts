import { expect, test, type Page } from "@playwright/test";

// mgmt-014 (EVID-017 §23, DEC-SCOPE-189): the investment register. The seeded §23 example (app.seed, MI14) shows 260%; a partner adds an
// investment and edits it, and the change reaches Management activity; the accountant and the super admin are refused (M13).

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("signed out, /management/investments sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/investments");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Finvestments$/);
});

test("a partner sees the §23 example at 260%, adds an investment and records its return", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("link", { name: "Investments & ROI" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Investments & ROI" })).toBeVisible();

  // The demo is dated 2026-04-01; filtering to that day keeps rows other runs added out of the way.
  await page.getByLabel("From", { exact: true }).fill("2026-04-01");
  await page.getByLabel("To", { exact: true }).fill("2026-04-01");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/date_from=2026-04-01/);
  const demo = page.getByRole("table", { name: "Investments" }).getByRole("row").filter({ hasText: "Marketing Campaign" }).filter({ hasText: "₹18,00,000.00" }).first();
  await expect(demo).toContainText("260.00%");

  const purpose = `E2E campaign ${Date.now()}`;
  await page.getByRole("button", { name: "Add investment" }).click();
  await page.getByLabel("Date").fill("2026-05-02");
  await page.getByLabel("Investor", { exact: true }).selectOption("partner");
  await page.getByLabel("Partner", { exact: true }).selectOption({ label: "Meera Partner" });
  await page.getByLabel("Amount (₹)").fill("200000");
  await page.getByLabel("Purpose").fill(purpose);
  await page.getByLabel("Business vertical").selectOption("it");
  await page.getByRole("button", { name: "Save investment" }).click();

  await expect(page).toHaveURL(/\/management\/investments\/[0-9a-f-]{36}$/);
  const record = page.getByRole("region", { name: "Investment record" });
  await expect(record).toContainText("Meera Partner");
  await expect(record).toContainText("₹2,00,000.00");
  await expect(record.getByText("ROI").locator("..")).toContainText("—");

  await page.getByRole("button", { name: "Edit investment" }).click();
  await page.getByLabel("Actual return (₹)").fill("500000");
  await page.getByLabel("Status").selectOption("completed");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText("Investment saved.");
  await expect(record.getByText("ROI").locator("..")).toContainText("150.00%");
  await expect(record).toContainText("Last changed by Arjun Partner");

  // §2 "who added an investment": the change is in the partner-only audit trail.
  await page.goto("/management/activity?kind=mgmt.investment");
  await expect(page.getByRole("list", { name: "Management activity" }).getByRole("listitem").first()).toContainText("Investment changed");
});

for (const [who, email, landing] of [["accountant", "accountant@edusphere.local", "/management"], ["super admin", "superadmin@edusphere.local", "/admin"]] as const) {
  test(`the ${who} is refused the register and has no entry for it (M13)`, async ({ page }) => {
    await signIn(page, email, landing);
    await page.goto("/management");
    await expect(page.getByRole("link", { name: "Investments & ROI" })).toHaveCount(0);
    await page.goto("/management/investments");
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(page.getByText("Only partners can open this")).toBeVisible();
  });
}
