import { expect, test, type Page } from "@playwright/test";

// pob-029 (DEC-SCOPE-437): the Team Lead opens Placement outcomes from the sidebar, regroups the period, drills into a group row and
// downloads the table; the page holds at phone width; a recruiter is refused. The figures' tie-out, the funnel, revenue gating, the
// "no invoices" edge and scope are covered by test_pob_029_outcome_reports.py.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

const PATH = "/recruiter/manager/placement-outcomes";

test("a Team Lead reads, regroups and exports placement outcomes", async ({ page }) => {
  await signIn(page, "admin", "placement.manager@edusphere.local");
  await page.goto("/recruiter/dashboard");
  await page.getByRole("link", { name: "Placement outcomes", exact: true }).first().click();
  await page.waitForURL((u) => u.pathname === PATH);
  await expect(page.getByRole("heading", { name: "Placement outcomes" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Conversions" })).toContainText("Offer acceptance");

  await page.locator("#outcomes-from").fill("2026-01-01");
  await page.locator("#outcomes-group").selectOption("recruiter");
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForURL((u) => u.search.includes("group_by=recruiter"));
  await expect(page.getByRole("heading", { name: "By recruiter" })).toBeVisible();

  const table = page.getByRole("region", { name: "Outcomes by recruiter" });
  if (await table.count()) {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
    expect(download.suggestedFilename()).toMatch(/^placement-outcomes-by-recruiter-.*\.csv$/);
    const first = table.locator("tbody th a").first();
    if (await first.count()) {
      await first.click();
      await page.waitForURL((u) => u.search.includes("recruiter="));
      await expect(page.getByRole("link", { name: "Clear the drill-down filter" })).toBeVisible();
    }
  } else {
    await expect(page.getByRole("status").filter({ hasText: "No offers were accepted in this period." })).toBeVisible();
  }

  await page.goto(`${PATH}?to=2099-01-01`);
  await expect(page.locator("p[role=alert]")).toHaveText("The range can't end in the future");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${PATH}?from=2026-01-01`);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("a recruiter is refused", async ({ page }) => {
  await signIn(page, "it", "placement@edusphere.local");
  await page.goto(PATH);
  await expect(page.getByText("Team Lead or administrator role required")).toBeVisible();
  expect((await page.request.get("/api/v1/recruiter/reports/placement-outcomes")).status()).toBe(403);
});
