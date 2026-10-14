import { expect, test, type Page } from "@playwright/test";

// mgmt-023 (spec UD1-UD14): the partner opens the University partnership dashboard from the Command Center, reads the twelve §19 KPIs
// (Revenue included), the pipeline and the expected partnerships, and a chosen period survives a reload; the super admin reaches it from
// their own sidebar without Revenue; the accountant is refused. The shared test database holds many rows, so the checks are about the
// page, not exact counts.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const kpis = (page: Page) => page.getByRole("list", { name: "University partnership KPIs" });

test("the partner reads the KPIs with Revenue, the pipeline and next month's expected partnerships, and keeps a chosen period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Universities", exact: true }).first().click();
  await page.waitForURL(/\/management\/universities/);
  await expect(page.getByRole("heading", { name: "University partnership dashboard" })).toBeVisible();

  await expect(kpis(page).getByRole("listitem")).toHaveCount(12);
  await expect(kpis(page).getByRole("listitem").last()).toContainText("Revenue");
  await expect(page.getByRole("list", { name: "Partnership pipeline" }).getByRole("listitem")).toHaveCount(8);
  await expect(page.getByRole("list", { name: "Expected partnerships" }).getByRole("listitem")).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Expected to sign next month" })).toBeVisible();

  await page.fill("#universities-from", "2025-03-01");
  await page.fill("#universities-to", "2025-03-31");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/from=2025-03-01&to=2025-03-31/);
  await page.reload();
  await expect(page.locator("#universities-from")).toHaveValue("2025-03-01");

  await page.fill("#universities-from", "2025-03-31");
  await page.fill("#universities-to", "2025-03-01");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("the super admin reaches the page from their own sidebar, without Revenue; the accountant is refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management university figures" }).first().click();
  await page.waitForURL(/\/management\/universities/);
  await expect(kpis(page).getByRole("listitem")).toHaveCount(11);
  await expect(page.getByRole("main").getByText("Revenue")).toHaveCount(0);
  await expect(page.getByRole("main").getByText(/Commission received/)).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/universities");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("on a phone the page does not scroll sideways", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/universities");
  await expect(kpis(page)).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
