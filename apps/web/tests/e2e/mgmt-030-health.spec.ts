import { expect, test, type Page } from "@playwright/test";

// mgmt-030 (spec BH1-BH14): the partner opens the Business health score from the Command Center, reads the overall score, twelve RAG
// lines and a breakdown whose points add up to the score, and a chosen month survives a reload; the super admin reaches it from their own
// sidebar with the six operational factors only; the accountant is refused. The shared test database holds many rows, so the checks are
// about the page and its arithmetic, not exact figures.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const lines = (page: Page) => page.getByRole("list", { name: "Health by factor" });

/** AC: the breakdown recomputes the overall score -- the points column adds up to the footer's score. */
async function expectPointsAddUp(page: Page) {
  const table = page.getByRole("table", { name: /Business health breakdown/ });
  const points = await table.locator("tbody tr td:last-child").allTextContents();
  const footer = table.locator("tfoot td");
  if ((await footer.count()) === 0) return; // not enough data to score
  const sum = points.filter((p) => p !== "—").reduce((a, p) => a + Number(p), 0);
  expect(sum).toBe(Number(await footer.textContent()));
}

test("the partner reads the overall score, twelve RAG lines and a breakdown that adds up, and keeps a chosen month", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Business health score", exact: true }).first().click();
  await page.waitForURL(/\/management\/health/);
  await expect(page.getByRole("heading", { name: "Business health score" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Overall health" })).toContainText("Overall business health");
  await expect(lines(page).getByRole("listitem")).toHaveCount(12);
  await expect(lines(page).getByRole("listitem").first()).toContainText("Revenue");
  await expectPointsAddUp(page);

  await page.getByLabel("Month", { exact: true }).fill("2025-03");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/month=2025-03/);
  await expect(page.getByText(/March 2025 compared with February 2025/)).toBeVisible();
  await page.reload();
  await expect(page.locator("#health-month")).toHaveValue("2025-03");
  await expectPointsAddUp(page);

  await page.goto("/management/health?month=2000-01");
  await expect(page.locator("p.empty[role=status]")).toHaveText("Not enough data to score January 2000.");
});

test("the super admin reaches the page from their own sidebar with the operational factors only; the accountant is refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management business health" }).first().click();
  await page.waitForURL(/\/management\/health/);
  await expect(page.getByRole("list", { name: "Overall health" })).toContainText("Operational health");
  await expect(lines(page).getByRole("listitem")).toHaveCount(6);
  for (const finance of ["Revenue", "Profit", "Cash flow", "Employee productivity", "Marketing ROI", "Expenses"]) {
    await expect(page.getByRole("rowheader", { name: finance, exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole("main").getByText("₹")).toHaveCount(0);
  await expect(page.getByRole("main")).not.toContainText(/margin|ROI|revenue/i); // QA30-01: no finance wording at all
  await expectPointsAddUp(page);

  await page.context().clearCookies();
  await signIn(page, "accountant@edusphere.local");
  await page.goto("/management/health");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("on a phone the page does not scroll sideways", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/health");
  await expect(lines(page)).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
