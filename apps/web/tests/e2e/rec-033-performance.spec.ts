import { expect, test, type Page } from "@playwright/test";

// rec-033 (AC1, AC2; PF1-PF9): the seeded placement manager opens Performance, sees the fifteen §24 figures and the per-recruiter
// table whose Total equals the sum of the rows, drills into one recruiter and back, and a recruiter is refused. The shared database keeps
// every earlier run's rows, so figures are compared through the AC2 rule rather than fixed numbers.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const number = (text: string | null) => Number((text ?? "").replace(/,/g, ""));

test("manager: fifteen figures, Total = sum of the recruiters, drill-down and back", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page, "admin", MANAGER);
  await page.getByRole("link", { name: "Performance" }).first().click();
  await page.waitForURL("**/recruiter/manager/performance");
  await expect(page.getByRole("heading", { name: "Recruiter performance", level: 2 })).toBeVisible();
  const tiles = page.getByRole("list", { name: "Team figures" });
  await expect(tiles.getByRole("listitem")).toHaveCount(15);

  const table = page.getByRole("region", { name: "Performance by recruiter" }).getByRole("table");
  const rows = table.locator("tbody tr");
  expect(await rows.count()).toBeGreaterThanOrEqual(2); // ≥ 1 recruiter + Unassigned
  await expect(rows.last().locator("th")).toHaveText("Unassigned");
  for (const column of [1, 3, 4]) { // Recruiter Leads, Requirements, Candidates Sourced (AC2)
    const cells = await rows.locator(`td:nth-of-type(${column})`).allTextContents();
    const total = number(await table.locator(`tfoot td:nth-of-type(${column})`).textContent());
    expect(cells.reduce((sum, cell) => sum + number(cell), 0)).toBe(total);
  }
  const leads = await table.locator("tfoot td:nth-of-type(1)").textContent();
  await expect(tiles.getByRole("listitem").first().locator("strong")).toHaveText(leads!);

  const first = rows.first().locator("th a");
  const name = (await first.textContent())!;
  await first.click();
  await page.waitForURL(/\/recruiter\/manager\/performance\?from=.*&recruiter=[0-9a-f-]{36}$/);
  await expect(page.getByRole("list", { name: `${name}'s figures` }).getByRole("listitem")).toHaveCount(15);
  await expect(page.getByRole("table")).toHaveCount(0);
  await page.getByRole("link", { name: "All recruiters" }).click();
  await page.waitForURL(/\/recruiter\/manager\/performance\?from=[\d-]+&to=[\d-]+$/);
  await expect(page.getByRole("list", { name: "Team figures" })).toBeVisible();

  const today = (await page.getByLabel("To").getAttribute("max"))!; // the browser itself refuses a day after today
  const yesterday = new Date(Date.parse(`${today}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("From").fill(today);
  await page.getByLabel("To").fill(yesterday);
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("The start date must not be after the end date");
  expect(errors).toEqual([]);
});

test("recruiter: refused", async ({ page }) => {
  await signIn(page, "it", RECRUITER);
  await page.goto("/recruiter/manager/performance");
  await expect(page.getByText("Placement manager or administrator role required")).toBeVisible();
});
