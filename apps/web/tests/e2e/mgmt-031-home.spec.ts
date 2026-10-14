import { expect, test, type Page } from "@playwright/test";

// mgmt-031 (spec HM1-HM14): a partner signs in and lands on the §31 home -- greeting, the month, seven snapshot figures and nine panels
// that each link to their page; the super admin gets the operational home with no money anywhere; the accountant's Command Center has no
// home. The shared test database holds many rows, so the checks are about the page, its panels and links, not exact figures.

const PANELS = ["Urgent issues", "Pending decisions", "Today's meetings", "Target vs actual", "Financial position", "Business growth", "My tasks", "Recent discussions", "Next month plan"];

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const tiles = (page: Page) => page.getByRole("list", { name: "Today's business snapshot" }).getByRole("listitem");

test("a partner lands on the home: greeting, seven figures and nine panels that open their pages", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await expect(page).toHaveURL(/\/management$/);
  await expect(page.getByRole("heading", { level: 2, name: /^Good (morning|afternoon|evening), / })).toBeVisible();
  await expect(tiles(page).locator("span")).toHaveText(["Revenue", "Expenses", "Profit", "Cash", "Students", "Applications", "Enrollments"]);
  await expect(tiles(page).first()).toContainText("₹");
  for (const panel of PANELS) await expect(page.getByRole("region", { name: panel, exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Management Command Center" })).toBeVisible(); // the pillars stay below

  await page.getByRole("region", { name: "Business growth" }).getByRole("link", { name: "Open the health score" }).click();
  await page.waitForURL(/\/management\/health$/);
  await page.goBack();
  await page.getByRole("region", { name: "Financial position" }).getByRole("link", { name: "Open accounts" }).click();
  await page.waitForURL(/\/management\/accounts/);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toHaveCount(0);
});

test("the super admin's home has no money; the accountant's Command Center has no home", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management");
  await expect(tiles(page).locator("span")).toHaveText(["Students", "Applications", "Enrollments"]);
  await expect(page.getByRole("region", { name: "Financial position" })).toHaveCount(0);
  for (const panel of PANELS.filter((p) => p !== "Financial position")) await expect(page.getByRole("region", { name: panel, exact: true })).toBeVisible();
  await expect(page.getByRole("main").getByText("₹")).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management");
  await expect(page.getByRole("heading", { level: 2, name: "Management Command Center" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Today's business snapshot" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Pending decisions" })).toHaveCount(0);
});

test("on a phone the home does not scroll sideways", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await expect(page.getByRole("region", { name: "Next month plan" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
