import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-036 (DEC-SCOPE-269, P1-P9): the overseas counselor's own performance report on their sidebar "Reports". Seeded demo accounts; the
// shared stack DB also holds backend-test rows, so the checks are on labels, shapes and behaviour, not fixed numbers.

const COUNSELOR = ["counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard"] as const;

test("the counselor reads their period and current figures, and the period stays in the address", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signIn(page, ...COUNSELOR);
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/reports$/);
  await expect(page.getByRole("heading", { name: "My performance", level: 2 })).toBeVisible();
  const period = page.getByRole("list", { name: "In the period" });
  for (const label of ["Leads assigned", "Conversions", "Conversion %", "Lead follow-ups due", "Follow-up completion %", "Tasks completed"]) {
    await expect(period.getByText(label, { exact: true })).toBeVisible();
  }
  const now = page.getByRole("list", { name: "Now" });
  for (const label of ["Overdue tasks", "Applications", "Offers", "Visas approved", "Enrolments"]) await expect(now.getByText(label, { exact: true })).toBeVisible();
  await expect(page.getByText(/revenue/i)).toHaveCount(0);

  await page.getByLabel("From").fill("2024-06-01");
  await page.getByLabel("To").fill("2024-06-30");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/from=2024-06-01&to=2024-06-30/);
  await expect(page.getByText(/2024 to .*2024, India time/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("From")).toHaveValue("2024-06-01");
  await page.getByRole("link", { name: "This month" }).click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/reports$/);
  expect(errors).toEqual([]);
});

test("an impossible period shows the reason and keeps the form", async ({ page }) => {
  await signIn(page, ...COUNSELOR);
  await page.goto("/overseas/counselor/reports?from=2024-06-30&to=2024-06-01");
  await expect(page.getByRole("alert").filter({ hasText: "The period must start on or before its end" })).toBeVisible(); // not Next's route announcer
  await expect(page.getByLabel("From")).toHaveValue("2024-06-30");
  await expect(page.getByRole("list", { name: "Now" })).toHaveCount(0);
});

test("the Overseas Admin is refused and the API refuses them too", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/counselor/reports");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  expect((await page.request.get("/api/v1/counselor/performance")).status()).toBe(403);
});

test("the report fits a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, ...COUNSELOR);
  await page.goto("/overseas/counselor/reports");
  await expect(page.getByRole("heading", { name: "My performance", level: 2 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
