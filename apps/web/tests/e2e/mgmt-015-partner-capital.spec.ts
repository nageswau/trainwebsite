import { expect, test, type Page } from "@playwright/test";

// mgmt-015 (EVID-017 §24, spec CP1-CP15): partner capital accounts. A partner opens the page from the Command Center, records a capital
// entry for the other partner and plans a share % change; both reach Management activity. The accountant and the super admin are refused
// (M13). The stack database is shared with the API tests, so this reads the seeded partners' columns and its own rows only.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("signed out, /management/capital sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/capital");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fcapital$/);
});

test("a partner records a capital entry and plans a share change", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("link", { name: "Partner capital accounts" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Partner capital accounts" })).toBeVisible();
  const accounts = page.getByRole("table", { name: "Capital accounts" });
  await expect(accounts.getByRole("columnheader", { name: "Arjun Partner" })).toBeVisible();
  await expect(accounts.getByRole("columnheader", { name: "Meera Partner" })).toBeVisible();
  await expect(accounts.getByRole("row", { name: /Capital balance/ })).toBeVisible();

  const note = `E2E capital ${Date.now()}`;
  await page.getByRole("button", { name: "Record a capital entry" }).click();
  await page.getByLabel("Partner", { exact: true }).selectOption({ label: "Meera Partner" });
  const today = await page.getByLabel("Date").getAttribute("max");
  await page.getByLabel("Date").fill(today!);
  await page.getByLabel("Kind").selectOption("additional");
  await page.getByLabel("Amount (₹)").fill("1234.56");
  await page.getByLabel("Note (optional)").fill(note);
  await page.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Capital entry recorded." })).toBeVisible();
  const mine = page.getByRole("table", { name: "Capital entries" }).getByRole("row").filter({ hasText: note });
  await expect(mine).toContainText("Meera Partner");
  await expect(mine).toContainText("Additional investment");
  await expect(mine).toContainText("₹1,234.56");

  // A share change planned for the same month next year shows in the history as planned, not in force.
  const [year, month] = today!.split("-").map(Number);
  const planned = `${year + 1}-${String(month).padStart(2, "0")}`;
  await page.getByRole("button", { name: "Set share %" }).click();
  await page.getByLabel("From the month").fill(planned);
  await page.getByLabel("Arjun Partner share %").fill("50");
  await page.getByLabel("Meera Partner share %").fill("50");
  await page.getByRole("button", { name: "Save shares" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Shares saved." })).toBeVisible();
  const history = page.getByRole("table", { name: "Share % history" }).getByRole("row").filter({ hasText: "Meera Partner" }).first();
  await expect(history).toContainText("Planned");

  await page.goto("/management/activity?kind=mgmt.capital");
  await expect(page.getByRole("list", { name: "Management activity" }).getByRole("listitem").first()).toContainText("Capital account");
});

for (const [who, email, landing] of [["accountant", "accountant@edusphere.local", "/management"], ["super admin", "superadmin@edusphere.local", "/admin"]] as const) {
  test(`the ${who} is refused capital accounts and has no entry for them (M13, AC4)`, async ({ page }) => {
    await signIn(page, email, landing);
    await page.goto("/management");
    await expect(page.getByRole("link", { name: "Partner capital accounts" })).toHaveCount(0);
    await page.goto("/management/capital");
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(page.getByText("Only partners can open this")).toBeVisible();
  });
}
