import { expect, test, type Page } from "@playwright/test";

// rec-035 (EVID-018 §26; MG1-MG8): the seeded placement manager opens the Management Dashboard from the menu and sees the seven totals
// and the two ranked lists; the period's Selected / Joined equal rec-033's Total (MG2); a recruiter is refused. The shared database keeps
// every earlier run's rows, so figures are compared across the two pages rather than to fixed numbers.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";

test("manager: seven totals, two ranked lists, Selected / Joined agree with Performance", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page, "admin", MANAGER);
  await page.getByRole("link", { name: "Management Dashboard" }).first().click();
  await page.waitForURL("**/recruiter/manager/business");
  await expect(page.getByRole("heading", { name: "Recruiter business", level: 2 })).toBeVisible();
  const tiles = page.getByRole("list", { name: "Recruiter business totals" }).getByRole("listitem");
  await expect(tiles).toHaveCount(7);
  await expect(page.getByRole("heading", { name: "Top Companies" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top Job Categories" })).toBeVisible();
  const selected = await tiles.nth(5).locator("strong").textContent();
  const joined = await tiles.nth(6).locator("strong").textContent();

  await page.goto("/recruiter/manager/performance");
  const figures = page.getByRole("list", { name: "Team figures" }).getByRole("listitem");
  await expect(figures.nth(6).locator("strong")).toHaveText(selected!);
  await expect(figures.nth(7).locator("strong")).toHaveText(joined!);

  await page.goto("/recruiter/manager/business");
  const today = (await page.getByLabel("To", { exact: true }).getAttribute("max"))!;
  const yesterday = new Date(Date.parse(`${today}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("From", { exact: true }).fill(today);
  await page.getByLabel("To", { exact: true }).fill(yesterday);
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("The start date must not be after the end date");
  expect(errors).toEqual([]);
});

test("recruiter: refused", async ({ page }) => {
  await signIn(page, "it", RECRUITER);
  await page.goto("/recruiter/manager/business");
  await expect(page.getByText("Placement manager or administrator role required")).toBeVisible();
});
