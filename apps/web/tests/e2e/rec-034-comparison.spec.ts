import { expect, test, type Page } from "@playwright/test";

// rec-034 (AC; BP1-BP4): the seeded placement manager opens Comparison, sees the twelve §25 metrics per recruiter under the two
// headings with a Total equal to the sum of the rows, narrows to one recruiter and back; the seeded recruiter sees only their own row.
// The shared database keeps every earlier run's rows, so figures are compared through the Total rule rather than fixed numbers.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const number = (text: string | null) => Number((text ?? "").replace(/[₹,]/g, ""));

test("manager: twelve metrics side by side, Total = sum of the recruiters, narrow and back", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page, "admin", MANAGER);
  await page.getByRole("link", { name: "Comparison", exact: true }).click();
  await page.waitForURL("**/recruiter/performance");
  await expect(page.getByRole("heading", { name: "Recruiter comparison", level: 2 })).toBeVisible();

  const table = page.getByRole("region", { name: "Performance by recruiter" }).getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Business development" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Recruitment" })).toBeVisible();
  await expect(table.locator("thead tr").nth(1).locator("th")).toHaveCount(13);
  const rows = table.locator("tbody tr");
  expect(await rows.count()).toBeGreaterThanOrEqual(1);
  for (const column of [1, 3, 7, 12]) { // Companies contacted, New recruiter leads, Candidates sourced, Revenue
    const cells = await rows.locator(`td:nth-of-type(${column})`).allTextContents();
    const total = number(await table.locator(`tfoot td:nth-of-type(${column})`).textContent());
    expect(cells.reduce((sum, cell) => sum + number(cell), 0)).toBeCloseTo(total, 2);
  }

  const first = rows.first().locator("th a");
  const name = (await first.textContent())!;
  await first.click();
  await page.waitForURL(/\/recruiter\/performance\?from=.*&recruiter=[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: `${name}'s figures` })).toBeVisible();
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1);
  await page.getByRole("link", { name: "All recruiters" }).click();
  await page.waitForURL(/\/recruiter\/performance\?from=[\d-]+&to=[\d-]+$/);
  await expect(page.getByRole("heading", { name: "Team figures" })).toBeVisible();

  const today = (await page.getByLabel("To").getAttribute("max"))!;
  const yesterday = new Date(Date.parse(`${today}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("From").fill(today);
  await page.getByLabel("To").fill(yesterday);
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("The start date must not be after the end date");
  expect(errors).toEqual([]);
});

test("recruiter: only their own row, no Total", async ({ page }) => {
  await signIn(page, "it", RECRUITER);
  await page.getByRole("link", { name: "My Performance" }).click();
  await page.waitForURL("**/recruiter/performance");
  await expect(page.getByRole("heading", { name: "My performance", level: 2 })).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await expect(table.locator("tfoot")).toHaveCount(0);
  await expect(table.locator("tbody a")).toHaveCount(0);
});
