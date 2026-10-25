import { expect, test, type Page } from "@playwright/test";

// mgmt-018 (spec CS1-CS12): the partner opens the Counseling dashboard from the Command Center, reads the §13 KPIs and the counselor-wise
// table (revenue included), and a chosen period survives a reload; the super admin reaches it from their own sidebar without revenue;
// the accountant is refused. The shared test database holds many rows, so the checks are about the page, not exact counts.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const kpis = (page: Page) => page.getByRole("list", { name: "Leads → Counseling → Conversion" });
const table = (page: Page) => page.getByRole("table", { name: "Counselor-wise performance" });

test("the partner reads the counseling KPIs and every counselor, and keeps a chosen period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Counseling", exact: true }).first().click();
  await expect(page).toHaveURL(/\/management\/counseling/);
  await expect(page.getByRole("heading", { name: "Counseling dashboard" })).toBeVisible();

  await expect(kpis(page).getByRole("listitem")).toHaveCount(7);
  await expect(kpis(page).getByRole("listitem").filter({ hasText: "Calls" })).not.toContainText("Not tracked"); // ccrm-004 LG6
  await expect(table(page).getByRole("columnheader", { name: "Calls" })).toBeVisible();
  await expect(kpis(page).getByRole("listitem").filter({ hasText: "Revenue" })).toContainText("₹");
  await expect(table(page).getByRole("columnheader", { name: "Revenue" })).toBeVisible();
  await expect(table(page).locator("tfoot")).toContainText("All counselors");

  await page.fill("#counseling-from", "2025-03-01");
  await page.fill("#counseling-to", "2025-03-31");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/from=2025-03-01&to=2025-03-31/);
  await page.reload();
  await expect(page.locator("#counseling-from")).toHaveValue("2025-03-01");

  await page.fill("#counseling-from", "2025-03-31");
  await page.fill("#counseling-to", "2025-03-01");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("the People Counselors entry opens the counselor table", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Counselors", exact: true }).first().click();
  await expect(page).toHaveURL(/\/management\/counseling#counselors/);
  await expect(table(page)).toBeVisible();
});

test("the super admin reaches the page from their own sidebar, without revenue; the accountant is refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management counseling figures" }).first().click();
  await expect(page).toHaveURL(/\/management\/counseling/);
  await expect(kpis(page).getByRole("listitem").filter({ hasText: "Revenue" })).toContainText("Partners only");
  await expect(table(page).getByRole("columnheader", { name: "Revenue" })).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/counseling");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("on a phone the page does not scroll sideways; the table scrolls in its own box", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/counseling");
  await expect(table(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
