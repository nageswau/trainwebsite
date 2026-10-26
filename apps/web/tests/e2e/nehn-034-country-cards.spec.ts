import { test, expect, type Page } from "@playwright/test";

// nehn-034 (DEC-SCOPE-286) -- country cards: flag, count, View universities (filtered), the student portal's Explore Countries page
// and the apply form's country step. Requires the seeded stack (Germany has published universities: TU Munich, RWTH Aachen).

async function germanyCard(page: Page) {
  await page.getByPlaceholder(/Search country/).fill("Germany");
  const card = page.locator("article.card").filter({ has: page.getByRole("heading", { name: "Germany", exact: true }) });
  await expect(card).toBeVisible();
  return card;
}

async function loginAsOverseasStudent(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");
}

test("a public country card shows flag, count and opens that country's universities (AC1)", async ({ page }) => {
  await page.goto("/overseas/countries");
  const card = await germanyCard(page);
  await expect(card.locator("img.country-flag")).toHaveAttribute("src", "/flags/de.svg");
  await expect(card.getByText(/^\d+ universit(y|ies)$/)).toBeVisible();
  await card.getByRole("link", { name: "View universities in Germany" }).click();
  await expect(page).toHaveURL(/\/overseas\/universities\?country=germany$/);
  await expect(page.getByRole("heading", { name: "Universities in Germany" })).toBeVisible();
  await page.getByPlaceholder(/Search university/).fill("RWTH Aachen");
  await expect(page.getByRole("heading", { name: "RWTH Aachen University" })).toBeVisible();
  await page.getByPlaceholder(/Search university/).fill("University of Manchester");
  await expect(page.getByRole("heading", { name: "University of Manchester" })).toHaveCount(0);
  await page.getByRole("link", { name: "All universities" }).click();
  await expect(page.getByRole("heading", { name: "Partner & Featured Universities" })).toBeVisible();
});

test("an unknown country filter shows the empty state, not an error", async ({ page }) => {
  await page.goto("/overseas/universities?country=no-such-country");
  await expect(page.getByText("Destination not found")).toBeVisible(); // QA-034-01
  await expect(page.getByRole("heading", { name: "No universities available" })).toBeVisible();
});

test("the student explores countries in the portal and applies with the country preselected (AC3)", async ({ page }) => {
  await loginAsOverseasStudent(page);
  await page.getByRole("link", { name: "Explore Countries" }).first().click();
  await expect(page.getByRole("heading", { name: "Explore Countries", level: 2 })).toBeVisible();
  const card = await germanyCard(page);
  await card.getByRole("link", { name: "Apply in Germany" }).click();
  await expect(page).toHaveURL(/\/overseas\/student\/applications\?country=germany$/);
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a University" }) });
  await expect(form.locator("#apply-country option:checked")).toHaveText("Germany");
  const universities = await form.locator("#apply-university option").allTextContents();
  expect(universities.slice(1).length).toBeGreaterThan(0);
  expect(universities.some((label) => label.startsWith("University of Manchester"))).toBe(false);
});

test("the explore countries page requires a session", async ({ page }) => {
  await page.goto("/overseas/student/explore-countries");
  await expect(page).toHaveURL(/\/overseas\/login/);
});

for (const width of [360, 1280]) {
  test(`country cards render at ${width}px without horizontal scroll (AC4)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/overseas/countries");
    const card = await germanyCard(page);
    await expect(card.getByRole("link", { name: "View universities in Germany" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await card.screenshot({ path: `test-results/nehn-034-card-${width}.png` });
  });
}
