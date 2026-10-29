import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-052: the Overseas Admin sees deposits paid and visas per university and opens a university's applications; the drill-down's
// count is the row's Applications and the way back keeps the filters. The shared stack DB also holds backend-test rows, so the checks
// are relational (row ↔ drill-down), not fixed numbers.

const NEW_COLUMNS = ["Deposits paid", "Visas approved", "Visas refused", "Visas pending"];

async function adminReports(page: Page) {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/crm-reports");
  await expect(page.getByRole("heading", { level: 2, name: "CRM reports" })).toBeVisible();
  return page.getByRole("table", { name: "University performance" });
}

test("the Overseas Admin opens a university's applications from the report and comes back with the filters", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const perf = await adminReports(page);
  for (const name of NEW_COLUMNS) await expect(perf.getByRole("columnheader", { name })).toBeVisible();

  // Narrow by the first intake so the URL carries a filter, then open the first university.
  const intake = await page.getByRole("form", { name: "Report filters" }).getByLabel("Intake", { exact: true }).locator("option").nth(1).getAttribute("value");
  await page.goto(`/overseas/admin/crm-reports?intake=${encodeURIComponent(intake!)}`);
  const row = page.getByRole("table", { name: "University performance" }).locator("tbody tr").first();
  const name = (await row.getByRole("rowheader").textContent())!.trim();
  const applications = Number((await row.getByRole("cell").first().textContent())!.replaceAll(",", ""));
  await row.getByRole("link", { name }).click();
  await page.waitForURL(/\/overseas\/admin\/crm-reports\/universities\/[0-9a-f-]{36}\?intake=/);

  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  await expect(page.getByText(new RegExp(`^${applications.toLocaleString("en-IN")} applications? — `))).toBeVisible();
  const table = page.getByRole("table", { name: `Applications at ${name}` });
  await expect(table.locator("tbody tr")).toHaveCount(Math.min(applications, 100));
  for (const header of ["Application", "Student", "Course", "Intake", "Stage", "Counselor", "Deposit paid", "Visa"]) {
    await expect(table.getByRole("columnheader", { name: header, exact: true })).toBeVisible();
  }
  for (const cell of await table.locator("tbody tr td:nth-child(4)").allTextContents()) expect(cell).toBe(intake);

  await page.getByRole("link", { name: /Back to CRM reports/ }).click();
  await page.waitForURL(`**/overseas/admin/crm-reports?intake=${encodeURIComponent(intake!).replaceAll("%20", "+")}`);
  await expect(page.getByLabel("Intake", { exact: true })).toHaveValue(intake!);
  expect(errors).toEqual([]);
});

test("an unknown university says so", async ({ page }) => {
  await adminReports(page);
  await page.goto("/overseas/admin/crm-reports/universities/00000000-0000-4000-8000-000000000000");
  await expect(page.locator(".form-error")).toHaveText("That university is not in the reports.");
  await expect(page.getByRole("link", { name: /Back to CRM reports/ })).toHaveAttribute("href", "/overseas/admin/crm-reports");
});

test("the drill-down fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  const perf = await adminReports(page);
  await perf.locator("tbody tr").first().getByRole("rowheader").getByRole("link").click();
  await page.waitForURL(/\/crm-reports\/universities\//);
  await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("a counselor is refused the drill-down", async ({ page }) => {
  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  expect((await page.request.get("/api/v1/management/crm-reports/universities/00000000-0000-4000-8000-000000000000/applications")).status()).toBe(403);
  await page.goto("/overseas/admin/crm-reports/universities/00000000-0000-4000-8000-000000000000");
  await expect(page.getByRole("table")).toHaveCount(0);
});
