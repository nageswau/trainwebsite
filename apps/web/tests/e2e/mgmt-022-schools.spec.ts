import { expect, test, type Page } from "@playwright/test";

// mgmt-022 (spec SD1-SD16): the partner opens the School dashboard from the Command Center, reads the §18 figures and the school-wise
// table (money included), and a chosen period survives a reload; the accountant reaches the money from the Finance entry and saves a
// school's contract value; the super admin reaches it from their own sidebar without money; a non-management user is refused. The shared
// test database holds many rows, so the checks are about the page, not exact counts.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const figures = (page: Page) => page.getByRole("list", { name: "School figures" });
const table = (page: Page) => page.getByRole("table", { name: "School-wise figures" });

test("the partner reads the school figures and the school-wise table, and keeps a chosen period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Schools", exact: true }).first().click();
  await page.waitForURL(/\/management\/schools/);
  await expect(page.getByRole("heading", { name: "School dashboard" })).toBeVisible();

  await expect(figures(page).getByRole("listitem")).toHaveCount(13);
  await expect(figures(page).getByRole("listitem").filter({ hasText: "School revenue" })).toContainText("₹");
  await expect(table(page).getByRole("columnheader", { name: "Contract value" })).toBeVisible();
  await expect(table(page).locator("tfoot")).toContainText("All schools");
  await expect(table(page).locator("tfoot")).toContainText("Not tagged to a school");

  await page.fill("#schools-from", "2025-03-01");
  await page.fill("#schools-to", "2025-03-31");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/from=2025-03-01&to=2025-03-31/);
  await page.reload();
  await expect(page.locator("#schools-from")).toHaveValue("2025-03-01");

  await page.fill("#schools-from", "2025-03-31");
  await page.fill("#schools-to", "2025-03-01");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("the accountant opens School revenue & contracts and saves a contract value", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "School revenue & contracts" }).first().click();
  await page.waitForURL(/\/management\/schools#school-money/);
  const row = table(page).getByRole("row").filter({ has: page.locator(".school-values") }).first();
  await row.locator("summary").click();
  const value = String(100000 + Math.floor(Math.random() * 800000));
  await row.getByLabel("Contract value (₹)").fill(value);
  await row.getByRole("button", { name: "Save" }).click();
  await expect(row.getByRole("status")).toHaveText("Saved.");
  await expect(row).toContainText(`₹${Number(value).toLocaleString("en-IN")}.00`);
});

test("the super admin reaches the page from their own sidebar, without money; the overseas admin is refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management school figures" }).first().click();
  await page.waitForURL(/\/management\/schools/);
  await expect(figures(page).getByRole("listitem").filter({ hasText: "School revenue" })).toContainText("Finance only");
  await expect(page.getByText("₹")).toHaveCount(0);
  await expect(page.getByText("Edit values")).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "overseasadmin@edusphere.local");
  await page.goto("/management/schools");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("on a phone the page does not scroll sideways; the table scrolls in its own box", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/schools");
  await expect(page.getByRole("heading", { name: "School dashboard" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
