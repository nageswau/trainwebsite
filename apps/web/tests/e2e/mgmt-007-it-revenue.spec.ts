import { expect, test, type Page } from "@playwright/test";

// mgmt-007 (spec IR1-IR12): the accountant opens IT Training revenue from the Command Center, the course rows add up (AC), the
// financial-year view survives a reload, and a payments link lists payments without student names; the super admin is refused. The
// shared test database holds many rows, so the checks look at the table's own sums, not exact figures.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const rupees = (text: string | null) => Number((text ?? "").replace(/[^\d.-]/g, ""));
const sum = (values: string[]) => values.map(rupees).reduce((a, b) => a + b, 0);

test("the accountant reads IT Training revenue for the financial year and opens a course's payments", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "IT Training revenue" }).first().click();
  await expect(page).toHaveURL(/\/management\/revenue\/it$/);
  await expect(page.getByRole("heading", { name: "IT Training revenue" })).toBeVisible();

  await page.getByLabel("Show").selectOption("year");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/period=year/);
  await expect(page.getByText(/^Financial year \d{4}-\d{2} to date:/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Show")).toHaveValue("year");

  const table = page.getByRole("table", { name: "Revenue per course" });
  await expect(table).toBeVisible(); // the seeded Python Full Stack enrolment is inside the financial year
  // AC: each course's revenue = its batch rows + its course-wide row; the courses + "Not linked" = the total.
  const groups = table.locator("tbody");
  const courseRevenue: number[] = [];
  for (let i = 0; i < (await groups.count()); i++) {
    const cells = await groups.nth(i).locator("tr td:nth-child(3)").allTextContents();
    expect(Math.abs(sum(cells.slice(1)) - rupees(cells[0]))).toBeLessThan(0.01);
    courseRevenue.push(rupees(cells[0]));
  }
  const foot = await table.locator("tfoot tr td:nth-child(3)").allTextContents();
  const total = rupees(foot[foot.length - 1]);
  const unlinked = foot.length > 1 ? rupees(foot[0]) : 0;
  expect(Math.abs(courseRevenue.reduce((a, b) => a + b, 0) + unlinked - total)).toBeLessThan(0.01);
  await expect(page.getByRole("list", { name: "IT Training figures" }).getByRole("listitem").first()).toContainText(foot[foot.length - 1].trim());

  const first = table.locator("tbody").first().getByRole("link", { name: /^Payments: / }).first();
  const course = ((await first.getAttribute("aria-label")) ?? "").replace("Payments: ", "");
  await first.click();
  await expect(page).toHaveURL(/period=year&program=[0-9a-f-]{36}#payments$/);
  const section = page.getByRole("region", { name: `Payments: ${course}` });
  await expect(section).toBeVisible();
  await expect(section.getByText(/No counted payments in this period\.|Student names are not shown\./)).toBeVisible();
  await expect(section).not.toContainText("Arjun Rao"); // the seeded IT student's name never shows (Q-32)
});

test("the super admin is refused IT Training revenue", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management/revenue/it");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Finance access required")).toBeVisible();
});
