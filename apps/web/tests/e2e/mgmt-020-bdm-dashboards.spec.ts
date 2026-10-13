import { expect, test, type Page } from "@playwright/test";

// mgmt-020 (spec BD1-BD12): the partner opens the BDM dashboards from the Command Center, walks the three type tabs (§16's 9 / 7 / 6
// figures), and a chosen period survives a reload and a tab switch; the super admin reaches it from their own sidebar; the accountant
// is refused. The shared test database holds many rows, so the checks are about the page, not exact counts.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const tabs = (page: Page) => page.getByRole("navigation", { name: "BDM types" });
const figureCount = async (page: Page) =>
  (await page.getByRole("list", { name: "In the period" }).getByRole("listitem").count()) +
  (await page.getByRole("list", { name: "Right now" }).getByRole("listitem").count().catch(() => 0));

test("the partner reads each BDM type's figures and keeps a chosen period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "BDM", exact: true }).first().click();
  await expect(page).toHaveURL(/\/management\/bdm/);
  await expect(page.getByRole("heading", { name: "BDM dashboards" })).toBeVisible();

  for (const [tab, type, count] of [["Agent BDM", "agent", 9], ["School BDM", "school", 7], ["College BDM", "college", 6]] as const) {
    await tabs(page).getByRole("link", { name: tab }).click();
    await expect(page).toHaveURL(new RegExp(`type=${type}`));
    await expect(tabs(page).getByRole("link", { name: tab })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("list", { name: "In the period" })).toBeVisible();
    expect(await figureCount(page)).toBe(count);
  }
  await expect(page.getByRole("list", { name: "In the period" }).getByRole("listitem").filter({ hasText: "Internships" })).toContainText("Not tracked");

  await page.fill("#bdm-dashboard-from", "2025-03-01");
  await page.fill("#bdm-dashboard-to", "2025-03-31");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/type=college&from=2025-03-01&to=2025-03-31/);
  await page.reload();
  await expect(page.locator("#bdm-dashboard-from")).toHaveValue("2025-03-01");
  await tabs(page).getByRole("link", { name: "Agent BDM" }).click();
  await expect(page).toHaveURL(/type=agent&from=2025-03-01&to=2025-03-31/);

  await page.fill("#bdm-dashboard-from", "2025-03-31");
  await page.fill("#bdm-dashboard-to", "2025-03-01");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("the super admin reaches the page from their own sidebar; the accountant is refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management BDM figures" }).first().click();
  await expect(page).toHaveURL(/\/management\/bdm/);
  await expect(page.getByRole("list", { name: "In the period" })).toBeVisible();

  await page.context().clearCookies();
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/bdm");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("on a phone the three tabs and every figure fit the screen", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/bdm?type=college");
  const current = tabs(page).getByRole("link", { name: "College BDM" });
  await expect(current).toBeInViewport({ ratio: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
