import { expect, test, type Page } from "@playwright/test";

// mgmt-003 (MS18, M13): the partner and the super admin open the Business snapshot from the Command Center and see the fifteen §3
// figures; the accountant has no entry and a direct visit shows the access card. Seeded demo accounts (MG12).

const LABELS = [
  "Total Students", "Active Students", "IT Training Students", "Abroad Education Students", "Agent Students", "Placement Students", "Active Agents",
  "Partner Schools", "University Partners", "Partner Companies", "Trainers", "Counselors", "Telecallers", "BDMs", "Recruiters",
]; // prettier-ignore

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function expectFifteenFigures(page: Page) {
  await expect(page.getByRole("heading", { level: 2, name: "Business snapshot" })).toBeVisible();
  const items = page.getByRole("list", { name: "Business snapshot figures" }).getByRole("listitem");
  await expect(items).toHaveCount(15);
  await expect(items.locator("span")).toHaveText(LABELS);
  for (const value of await items.locator("strong").allTextContents()) expect(value).toMatch(/^\d[\d,]*$/);
}

test("a partner opens the Business snapshot from the Command Center", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "Business Intelligence" }).getByRole("link", { name: "Business snapshot" }).click();
  await page.waitForURL("**/management/snapshot");
  await expectFifteenFigures(page);
  await page.getByRole("link", { name: "Command Center" }).first().click();
  await page.waitForURL(/\/management$/);
});

test("the super admin sees the snapshot too (operational tier)", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management/snapshot");
  await expectFifteenFigures(page);
});

test("the accountant has no entry, and a direct visit is refused", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await expect(page.getByRole("link", { name: "Business snapshot" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/management/snapshot")).status()).toBe(403);
  await page.goto("/management/snapshot");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Operational access required")).toBeVisible();
});

test("signed out, the snapshot sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/snapshot");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fsnapshot$/);
});
