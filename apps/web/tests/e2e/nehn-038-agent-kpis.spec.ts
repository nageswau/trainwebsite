import { test, expect, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";

// nehn-038 (DEC-SCOPE-306) -- the agency dashboard's remaining KPIs and its referral-date filter. Requires the stack running with
// `python -m app.seed` applied (the seeded agency has students and applications).

const MASTER = "agent@edusphere.local";

function value(page: Page, label: string) {
  return page.locator(".kpi-tile").filter({ has: page.getByText(label, { exact: true }) }).locator(".kpi-value");
}

test("a Master sees submitted, visa outcomes and conversion, and the date filter narrows them (nehn-038)", async ({ page }) => {
  await signIn(page, MASTER, "Demo@123");
  await page.goto("/overseas/agent/dashboard");
  for (const heading of ["Pipeline", "Visa outcomes", "Conversion"]) {
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
  await expect(value(page, "Applications submitted")).toHaveText(/^\d[\d,]*$/);
  await expect(value(page, "Conversion rate")).toHaveText(/^(—|\d+(\.\d)?%)$/);
  await expect(page.getByText(/Students referred at any time/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Staff performance" }).or(page.getByText(/No staff yet/))).toBeVisible();
  const pendingActions = await value(page, "Pending actions").textContent();

  // A range nobody was referred in: every cohort figure is zero, the rate a dash, and the work queues stay current (D2).
  const form = page.getByRole("form", { name: "Dashboard date range" });
  await form.getByLabel("Referred from").fill("2000-01-01");
  await form.getByLabel("Referred to").fill("2000-01-31");
  await form.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/from=2000-01-01&to=2000-01-31/);
  await expect(page.getByText(/Students referred 2000-01-01 to 2000-01-31/)).toBeVisible();
  for (const label of ["Total students", "Applications", "Applications submitted", "Visa decisions", "Conversions"]) {
    await expect(value(page, label)).toHaveText("0");
  }
  await expect(value(page, "Conversion rate")).toHaveText("—");
  await expect(value(page, "Pending actions")).toHaveText(pendingActions ?? "");
  await expect(page.getByLabel("Referred from")).toHaveValue("2000-01-01");

  await page.reload();
  await expect(page.getByLabel("Referred to")).toHaveValue("2000-01-31");
  // QA38-01: Back shows the previous page's range in the inputs, not the dates typed before Apply.
  await page.goBack();
  await expect(page).toHaveURL(/\/overseas\/agent\/dashboard$/);
  await expect(page.getByLabel("Referred from")).toHaveValue("");
  await expect(page.getByLabel("Referred to")).toHaveValue("");
  await page.goForward();
  await page.getByRole("link", { name: "Clear dates" }).click();
  await expect(page).toHaveURL(/\/overseas\/agent\/dashboard$/);
  await expect(page.getByText(/Students referred at any time/)).toBeVisible();
});

test("a reversed range is refused with a field message and the form kept (nehn-038)", async ({ page }) => {
  await signIn(page, MASTER, "Demo@123");
  await page.goto("/overseas/agent/dashboard?from=2026-03-31&to=2026-03-01");
  await expect(page.locator(".form-error")).toHaveText("'Referred to' must be on or after 'Referred from'");
  await expect(page.getByLabel("Referred from")).toHaveValue("2026-03-31");
  await expect(page.getByLabel("Referred to")).toHaveAttribute("aria-invalid", "true");
  await page.getByRole("link", { name: "Clear dates" }).click();
  await expect(page.getByRole("heading", { name: "Conversion", exact: true })).toBeVisible();
});

test("malformed dates in the address are ignored (nehn-038)", async ({ page }) => {
  await signIn(page, MASTER, "Demo@123");
  await page.goto("/overseas/agent/dashboard?from=yesterday&to=2026-13-45");
  await expect(page.getByText(/Students referred at any time/)).toBeVisible();
  await expect(page.locator(".form-error")).toHaveCount(0);
});

for (const width of [375, 768]) {
  test(`the filter and new tiles fit a ${width} px screen (nehn-038)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page, MASTER, "Demo@123");
    await page.goto("/overseas/agent/dashboard?from=2020-01-01");
    await expect(page.getByRole("heading", { name: "Visa outcomes", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByRole("button", { name: "Apply" })).toBeInViewport();
  });
}
