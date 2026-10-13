import { expect, test, type Page } from "@playwright/test";

// mgmt-008 (spec RR1-RR12): the accountant opens Recruitment revenue from the Command Center, the kind rows add up to the total, revenue
// per placement is the total ÷ joining (AC1), and the financial-year view survives a reload; the super admin reaches the KPI-only page
// from their own sidebar and sees no money. The shared test database holds many rows, so the checks use the page's own figures.

async function signIn(page: Page, email: string, portal = "admin") {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const rupees = (text: string | null) => Number((text ?? "").replace(/[^\d.-]/g, ""));

async function tile(page: Page, label: string): Promise<string> {
  return (await page.getByRole("list", { name: "Recruitment KPIs" }).getByRole("listitem").filter({ hasText: label }).locator("strong").textContent()) ?? "";
}

test("the accountant reads Recruitment revenue and the nine KPIs, for the month and the financial year", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Recruitment revenue" }).first().click();
  await expect(page).toHaveURL(/\/management\/revenue\/recruitment$/);
  await expect(page.getByRole("heading", { name: "Recruitment & Placement revenue" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Recruitment KPIs" }).getByRole("listitem")).toHaveCount(9);

  await page.getByLabel("Show").selectOption("year");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/period=year/);
  await expect(page.getByText(/^Financial year \d{4}-\d{2} to date:/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Show")).toHaveValue("year");

  const table = page.getByRole("table", { name: "Revenue by kind" });
  if (await table.isVisible()) {
    const amounts = await table.locator("tbody td").allTextContents();
    const total = rupees(await table.locator("tfoot td").textContent());
    expect(Math.abs(amounts.map(rupees).reduce((a, b) => a + b, 0) - total)).toBeLessThan(0.01);
    const joining = Number(await tile(page, "Joining"));
    const perPlacement = await tile(page, "Revenue per placement");
    if (joining > 0) expect(Math.abs(rupees(perPlacement) - total / joining)).toBeLessThan(0.01); // AC1
    else expect(perPlacement).toBe("—");
  } else {
    await expect(page.getByRole("status").filter({ hasText: "No recruitment revenue" })).toBeVisible();
  }
});

test("the super admin opens the KPI page from their sidebar and sees no money", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Recruitment KPIs" }).first().click();
  await expect(page).toHaveURL(/\/management\/revenue\/recruitment$/);
  await expect(page.getByRole("heading", { name: "Recruitment & Placement KPIs" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Recruitment KPIs" }).getByRole("listitem")).toHaveCount(8);
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.locator(".portal-content")).not.toContainText("₹");
});

test("a recruiter is refused the page", async ({ page }) => {
  await signIn(page, "placement@edusphere.local", "it");
  await page.goto("/management/revenue/recruitment");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
