import { expect, test, type Page } from "@playwright/test";

// mgmt-002 (EVID-017 §2, DEC-SCOPE-187 MA5/MA6): the seeded demo activity (app.seed, MA12) seen through each tier. Partner Two sees that
// Partner One approved an expense; the accountant sees ledger entries but never the investment; the super admin sees operational kinds.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const list = (page: Page) => page.getByRole("list", { name: "Management activity" });

test("signed out, /management/activity sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/activity");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Factivity$/);
});

test("a partner sees every kind and filters by who and what", async ({ page }) => {
  await signIn(page, "partner.two@edusphere.local", "/management");
  await page.getByRole("link", { name: "Management activity" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Management activity" })).toBeVisible();
  await expect(list(page).getByText("Investment created").first()).toBeVisible();

  await page.getByLabel("Done by").selectOption({ label: "Arjun Partner (Partner)" });
  await page.getByLabel("Kind").selectOption({ label: "Ledger entry" });
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/kind=mgmt.ledger/);
  const approved = list(page).getByRole("listitem").filter({ hasText: "DEMO-EXP-1" }).filter({ hasText: "Ledger entry approved" });
  await expect(approved).toContainText("status: pending → approved");
  await expect(approved).toContainText("by Arjun Partner (Partner)");
  await expect(list(page).getByText("Investment created")).toHaveCount(0);

  await page.reload(); // the filters live in the address
  await expect(page.getByLabel("Kind")).toHaveValue("mgmt.ledger");
  await page.getByRole("link", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/management\/activity$/);
});

test("an accountant never sees investment entries, even by asking for them (AC2)", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await page.goto("/management/activity");
  await expect(list(page).getByText("Ledger entry changed").first()).toBeVisible();
  await expect(list(page).getByText("Investment created")).toHaveCount(0);
  await expect(page.getByLabel("Kind").locator("option")).toHaveText(["All kinds", "Ledger entry"]);
  const asked = await page.request.get("/api/v1/management/activity?kind=mgmt.investment");
  expect(asked.status()).toBe(200);
  expect((await asked.json()).items).toEqual([]);
});

test("the super admin sees operational kinds only; capital returns none", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management/activity");
  await expect(list(page).getByText("Task completed").first()).toBeVisible();
  await expect(list(page).getByText("Ledger entry approved")).toHaveCount(0);
  const capital = await (await page.request.get("/api/v1/management/activity?kind=mgmt.capital")).json();
  expect(capital.total).toBe(0);
  await page.goto("/management/activity?date_from=2026-02-02&date_to=2026-02-01");
  await expect(page.getByRole("alert")).toHaveText("The end date must be on or after the start date");
});

test("an IT admin cannot open it", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
  await page.goto("/management/activity");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
