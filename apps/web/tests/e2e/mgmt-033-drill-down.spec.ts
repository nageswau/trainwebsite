import { expect, test, type Page } from "@playwright/test";

// mgmt-033 (spec DD1-DD14): the accountant drills IT Training revenue for the financial year from the dashboard down to one payment's
// record -- at every level the rows add up to the figure above (AC1), the breadcrumbs keep the path, the last level is the record
// read-only (AC2); a tampered path gets a message; the super admin is refused (AC3). The shared test database holds many rows, so the
// checks follow the first row at each level and compare the table's own sums, not exact figures.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const rupees = (text: string | null) => Number((text ?? "").replace(/[^\d.-]/g, ""));

test("the accountant drills IT Training revenue from the dashboard down to a payment record", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/revenue/it?period=year");
  const headline = await page.getByRole("list", { name: "IT Training figures" }).getByRole("listitem").first().locator("strong").textContent();
  await page.getByRole("link", { name: "Drill down into this revenue" }).click();
  await page.waitForURL(/\/management\/drill\/it\?month=\d{4}-\d{2}&period=year$/);
  await expect(page.getByRole("heading", { name: "IT Training revenue: drill-down" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Drill-down figures" }).getByRole("listitem").first()).toContainText((headline ?? "").trim()); // level 0 = the dashboard

  const levels = ["course", "batch", "trainer", "student", "payment"];
  for (const [depth, level] of levels.entries()) {
    const table = page.getByRole("table", { name: `By ${level}` });
    await expect(table).toBeVisible();
    const amounts = await table.locator("tbody tr td:nth-child(3)").allTextContents();
    const total = rupees(await table.locator("tfoot td:nth-child(3)").textContent());
    if (!(await page.getByText(/^Showing /).isVisible())) expect(Math.abs(amounts.map(rupees).reduce((a, b) => a + b, 0) - total)).toBeLessThan(0.01); // AC1
    const first = table.locator("tbody tr").first().getByRole("link");
    const name = (await first.textContent()) ?? "";
    await first.click();
    await page.waitForURL((url) => (url.searchParams.get("path") ?? "").split(",").length === depth + 1);
    await expect(page.getByRole("navigation", { name: "Drill-down path" }).locator('[aria-current="page"]')).toHaveText(name);
  }

  const record = page.getByRole("region", { name: "Payment record" });
  await expect(record).toBeVisible(); // AC2: the record, read-only
  await expect(record.locator("input, button, form")).toHaveCount(0);
  await expect(page.getByText(/recorded in Management activity/)).toBeVisible();
  await page.reload();
  await expect(record).toBeVisible();

  await page.getByRole("navigation", { name: "Drill-down path" }).getByRole("link", { name: "IT Training revenue" }).click();
  await page.waitForURL((url) => !url.searchParams.has("path"));
  await expect(page.getByRole("table", { name: "By course" })).toBeVisible();
});

test("a tampered path shows a message and a way back", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/drill/it?path=00000000-0000-4000-8000-000000000000");
  await expect(page.locator(".form-error")).toHaveText("Nothing to show for this selection in this period");
  await page.getByRole("link", { name: "Start again from the top" }).click();
  await page.waitForURL((url) => !url.searchParams.has("path"));
});

test("the super admin cannot open a money chain", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/drill/abroad");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
