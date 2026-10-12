import { expect, test, type Page } from "@playwright/test";

// mgmt-005 (spec MA1-MA12): the accountant switches the ledger to "Manual + automatic" and sees paid student fees as read-only automatic
// IT income lines (source badge, no link), and the choice survives a reload; the super admin is refused. The shared test database holds
// many lines, so the checks look for the automatic rows' shape, not exact counts.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("the accountant sees paid IT fees as automatic income lines", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/ledger");
  await page.getByRole("combobox", { name: "Lines" }).selectOption({ label: "Manual + automatic" });
  await page.getByRole("combobox", { name: "Kind" }).selectOption({ label: "Income" });
  await page.getByRole("combobox", { name: "Vertical" }).selectOption({ label: "IT Training" });
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/include=auto/);

  const totals = page.getByRole("list", { name: "Totals" });
  await expect(totals.getByRole("listitem").filter({ hasText: "Income (approved + automatic)" })).toBeVisible();
  const autoRow = page.getByRole("row").filter({ hasText: "Automatic · Student payment · Income" }).first();
  await expect(autoRow).toBeVisible();
  await expect(autoRow.getByRole("link")).toHaveCount(0);
  await expect(autoRow.getByText("Automatic", { exact: true })).toBeVisible();
  await expect(autoRow).toContainText("IT training");
  await expect(autoRow).toContainText("₹");

  await page.reload();
  await expect(page.getByRole("combobox", { name: "Lines" })).toHaveValue("auto");
  await expect(page.getByRole("row").filter({ hasText: "Automatic · Student payment" }).first()).toBeVisible();

  // Manual-only (the mgmt-004 view) never shows an automatic line.
  await page.getByRole("combobox", { name: "Lines" }).selectOption({ label: "Manual entries only" });
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).not.toHaveURL(/include=auto/);
  await expect(page.getByRole("row").filter({ hasText: "Automatic ·" })).toHaveCount(0);
});

test("the super admin is refused the ledger with automatic lines", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/ledger?include=auto");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
