import { expect, test, type Page } from "@playwright/test";

// mgmt-019 (§14, spec TC1-TC16, M13): the partner opens the Telecalling dashboard from the Command Center, sees the eight §14 figures,
// conversion, the chain and the two tables, and changes the URL-held period; the super admin sees it too; the accountant is refused.
// Seeded demo accounts. The shared stack DB also holds backend-test rows, so the checks are relational (totals = sums), not fixed numbers.

const FIGURES = ["Leads assigned", "Calls attempted", "Connected", "Interested", "Follow-up", "Appointment", "Converted", "Lost", "Telecaller conversion"];

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const number = (text: string | null) => Number(text!.replaceAll(",", ""));

test("a partner opens the dashboard from the Command Center and changes the period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "Sales" }).getByRole("link", { name: "Leads & calls" }).click();
  await page.waitForURL("**/management/telecalling");
  await expect(page.getByRole("heading", { level: 2, name: "Telecalling" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Company telecalling figures" }).getByRole("listitem").locator("span")).toHaveText(FIGURES);
  await expect(page.getByRole("list", { name: "Calls to registration" }).locator(".funnel-label")).toHaveText(["Calls", "Interested", "Counseling", "Registration"]);

  // AC1 on screen: the Company row is the sum of the team rows (calls column).
  const teams = page.getByRole("table", { name: "Telecalling by team" }).locator("tbody tr");
  await expect(teams).toHaveCount(3);
  const calls = async (row: number) => number(await teams.nth(row).locator("td").nth(2).textContent());
  expect((await calls(0)) + (await calls(1))).toBe(await calls(2));

  const form = page.getByRole("form", { name: "Telecalling period" });
  const firstOfMonth = await form.getByLabel("From").inputValue(); // QA19-01: the default period is in the inputs
  const today = await form.getByLabel("To").inputValue();
  expect(firstOfMonth).toBe(today.slice(0, 8) + "01");
  await form.getByLabel("From").fill(today); // just today
  await form.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(`**/management/telecalling?date_from=${today}&date_to=${today}`);
  await page.reload();
  await expect(page.getByRole("form", { name: "Telecalling period" }).getByLabel("From")).toHaveValue(today);
  await page.getByRole("link", { name: "This month" }).click();
  await page.waitForURL(/\/management\/telecalling$/);
  await expect(page.getByRole("form", { name: "Telecalling period" }).getByLabel("From")).toHaveValue(firstOfMonth); // QA19-02
});

test("the People pillar's Telecallers entry lands on the per-telecaller table", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "People" }).getByRole("link", { name: "Telecallers" }).click();
  await page.waitForURL("**/management/telecalling#telecallers");
  await expect(page.getByRole("heading", { name: "By telecaller" })).toBeInViewport();
});

test("a period ending in the future shows the API's words", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.goto("/management/telecalling?date_to=2999-01-01");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The range can't end in the future");
});

test("the super admin sees the dashboard too (operational tier)", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management/telecalling");
  await expect(page.getByRole("list", { name: "Company telecalling figures" }).getByRole("listitem")).toHaveCount(9);
});

test("the accountant has no entry, and a direct visit is refused", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await expect(page.getByRole("link", { name: "Leads & calls" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/management/telecalling")).status()).toBe(403);
  await page.goto("/management/telecalling");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
