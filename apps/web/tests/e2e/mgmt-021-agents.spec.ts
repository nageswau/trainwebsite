import { expect, test, type Page } from "@playwright/test";

// mgmt-021 (spec AN1-AN14): the partner opens the Agent network dashboard from the Command Center, reads the §17 figures, the chain and
// the agency ranking (money included), and a chosen period survives a reload; the super admin reaches it from their own sidebar without
// money; the accountant is refused. The shared test database holds many rows, so the checks are about the page, not exact counts.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const figures = (page: Page) => page.getByRole("list", { name: "Agent network figures" });
const table = (page: Page) => page.getByRole("table", { name: "Agency-wise performance" });

test("the partner reads the agent figures, the chain and the ranking, and keeps a chosen period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Agents", exact: true }).first().click();
  await page.waitForURL(/\/management\/agents/);
  await expect(page.getByRole("heading", { name: "Agent network dashboard" })).toBeVisible();

  await expect(figures(page).getByRole("listitem")).toHaveCount(12);
  await expect(figures(page).getByRole("listitem").filter({ hasText: "Revenue" })).toContainText("₹");
  await expect(page.getByRole("list", { name: "Agent → Staff → Student → Application → Enrollment → Revenue" })).toBeVisible();
  await expect(table(page).getByRole("columnheader", { name: "Revenue" })).toBeVisible();
  await expect(table(page).locator("tfoot")).toContainText("All agencies");

  await page.fill("#agents-from", "2025-03-01");
  await page.fill("#agents-to", "2025-03-31");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/from=2025-03-01&to=2025-03-31/);
  await page.reload();
  await expect(page.locator("#agents-from")).toHaveValue("2025-03-01");

  await page.fill("#agents-from", "2025-03-31");
  await page.fill("#agents-to", "2025-03-01");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("the super admin reaches the page from their own sidebar, without money; the accountant is refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management agent figures" }).first().click();
  await page.waitForURL(/\/management\/agents/);
  await expect(figures(page).getByRole("listitem").filter({ hasText: "Commission" })).toContainText("Partners only");
  await expect(figures(page).getByRole("listitem").filter({ hasText: "Revenue" })).toContainText("Partners only");
  await expect(page.getByText("₹")).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/agents");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("on a phone the page does not scroll sideways; the table scrolls in its own box", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/agents");
  await expect(page.getByRole("heading", { name: "Agent network dashboard" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
