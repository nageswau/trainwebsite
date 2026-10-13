import { expect, test, type Page } from "@playwright/test";

// mgmt-006 (spec MR1-MR12): a partner opens the Abroad Education revenue dashboard from the Command Center and sees the university
// commission kind; every breakdown (+ Unattributed) adds up to revenue and the contribution = revenue - expenses. The accountant sees the
// figures without university commission and a note saying so; the super admin is refused. The shared test database holds many lines,
// so the checks look at the tables' shape and their own sums, not exact figures.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const rupees = (text: string) => Number(text.replace(/[^\d.-]/g, ""));
const near = (a: number, b: number) => expect(Math.abs(a - b)).toBeLessThan(0.01);

async function annual(page: Page, region: string): Promise<{ rows: number[]; total: number }> {
  const table = page.getByRole("region", { name: region }).getByRole("table");
  const rows = (await table.locator("tbody tr td:nth-child(3)").allTextContents()).map(rupees);
  return { rows, total: rupees((await table.locator("tfoot tr td:nth-child(3)").textContent()) ?? "") };
}

test("a partner reads the Abroad revenue dashboard, whose breakdowns add up to revenue", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Abroad Education revenue" }).first().click();
  await expect(page).toHaveURL(/\/management\/revenue\/abroad$/);
  await expect(page.getByRole("heading", { level: 2, name: "Abroad Education revenue" })).toBeVisible();

  const kinds = page.getByRole("table", { name: "Revenue by kind" });
  await expect(kinds.getByRole("rowheader")).toHaveText(["Student service fees", "Application-related & other student payments", "University commission", "Recorded in the ledger", "Total revenue"]);
  const kindYear = (await kinds.locator("tbody tr td:nth-child(3)").allTextContents()).map(rupees);
  const revenue = rupees((await kinds.locator("tfoot tr td:nth-child(3)").textContent()) ?? "");
  near(kindYear.reduce((a, b) => a + b, 0), revenue);
  // AC: the sum of each breakdown + Unattributed = Abroad revenue.
  for (const region of ["Country-wise revenue", "University-wise revenue", "Intake-wise revenue", "Agency-wise revenue"]) {
    const { rows, total } = await annual(page, region);
    near(rows.reduce((a, b) => a + b, 0), revenue);
    near(total, revenue);
  }
  // AC: contribution = revenue - expenses.
  const summary = page.getByRole("table", { name: "Abroad Education summary" });
  const [rev, spent, contribution] = (await summary.locator("tbody tr td:nth-child(3)").allTextContents()).map(rupees);
  near(rev, revenue);
  near(contribution, rev - spent);
  await expect(page.getByText(/shown to partners only/)).toHaveCount(0);

  await page.getByLabel("Month", { exact: true }).fill("2025-04");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/month=2025-04/);
  await page.reload();
  await expect(page.getByLabel("Month", { exact: true })).toHaveValue("2025-04");
  await expect(page.getByRole("link", { name: /Abroad lines in the ledger/ })).toHaveAttribute("href", "/management/ledger?month=2025-04&vertical=abroad&include=auto");
});

test("the accountant sees Abroad revenue without university commission", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/revenue/abroad");
  await expect(page.getByText(/University commission is shown to partners only/)).toBeVisible();
  const kinds = page.getByRole("table", { name: "Revenue by kind" });
  await expect(kinds.getByRole("rowheader")).toHaveText(["Student service fees", "Application-related & other student payments", "Recorded in the ledger", "Total revenue"]);
});

test("the super admin is refused the Abroad revenue dashboard", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/revenue/abroad");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
