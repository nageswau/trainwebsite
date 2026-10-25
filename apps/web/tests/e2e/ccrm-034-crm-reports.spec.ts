import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-034 (DEC-SCOPE-263, R1-R10): the partner opens the CRM reports from the Command Center, sees the six reports with students and
// applications counted separately and narrows them with URL-held filters; the Overseas Admin reads the same reports from their sidebar;
// the accountant and the counselor are refused. Seeded demo accounts; the shared stack DB also holds backend-test rows, so the checks are
// relational (a filter never raises a total), not fixed numbers.

async function adminSignIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const REPORTS = ["Application ageing", "University performance", "Visa outcomes", "Document readiness", "Lead conversion by intake", "Forecast by intake"];

async function universitiesTotal(page: Page): Promise<number> {
  const total = page.getByRole("table", { name: "University performance" }).getByRole("row", { name: /^Total/ }).getByRole("cell").first();
  return Number((await total.textContent())!.replaceAll(",", ""));
}

test("a partner opens the CRM reports from the Command Center and narrows them by destination", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await adminSignIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "Students" }).getByRole("link", { name: "CRM reports" }).click();
  await page.waitForURL("**/management/crm-reports");
  await expect(page.getByRole("heading", { level: 2, name: "CRM reports" })).toBeVisible();
  for (const name of REPORTS) await expect(page.getByRole("heading", { level: 3, name })).toBeVisible();
  const perf = page.getByRole("table", { name: "University performance" });
  await expect(perf.getByRole("columnheader", { name: "Students" })).toBeVisible();
  await expect(perf.getByRole("columnheader", { name: "Applications" })).toBeVisible();
  const all = await universitiesTotal(page);

  const form = page.getByRole("form", { name: "Report filters" });
  const destination = form.getByLabel("Destination");
  const country = await destination.locator("option").nth(1).getAttribute("value");
  await destination.selectOption(country!);
  await form.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(new RegExp(`/management/crm-reports\\?country=${country}$`)); // the empty fields are dropped
  expect(await universitiesTotal(page)).toBeLessThanOrEqual(all);

  await page.reload(); // the filter lives in the address
  await expect(page.getByRole("form", { name: "Report filters" }).getByLabel("Destination")).toHaveValue(country!);
  await page.getByRole("link", { name: "Clear filters" }).click();
  await page.waitForURL(/\/management\/crm-reports$/);
  expect(await universitiesTotal(page)).toBe(all);

  await page.getByRole("form", { name: "Report filters" }).getByLabel("Created from").fill("2027-02-01");
  await page.getByRole("form", { name: "Report filters" }).getByLabel("Created to").fill("2027-01-01");
  await page.getByRole("form", { name: "Report filters" }).getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "end date" })).toHaveText("The end date must be on or after the start date");
  expect(errors).toEqual([]);
});

test("the Overseas Admin reads the same reports from the sidebar", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.getByRole("link", { name: "CRM reports" }).click();
  await page.waitForURL("**/overseas/admin/crm-reports");
  for (const name of REPORTS) await expect(page.getByRole("heading", { level: 3, name })).toBeVisible();
  await expect(page.getByRole("form", { name: "Report filters" })).toHaveAttribute("action", "/overseas/admin/crm-reports");
});

test("the accountant and the counselor are refused", async ({ browser }) => {
  const accountant = await (await browser.newContext()).newPage();
  await adminSignIn(accountant, "accountant@edusphere.local", "/management");
  await expect(accountant.getByRole("link", { name: "CRM reports" })).toHaveCount(0);
  expect((await accountant.request.get("/api/v1/management/crm-reports")).status()).toBe(403);
  await accountant.goto("/management/crm-reports");
  await expect(accountant.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  const counselor = await (await browser.newContext()).newPage();
  await signIn(counselor, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  expect((await counselor.request.get("/api/v1/management/crm-reports")).status()).toBe(403);
  await counselor.goto("/overseas/admin/crm-reports");
  await expect(counselor.getByRole("table")).toHaveCount(0);
});

test("on a phone the wide tables scroll inside their cards, not the page (QA-01)", async ({ browser }) => {
  const page = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await adminSignIn(page, "partner.one@edusphere.local", "/management");
  await page.goto("/management/crm-reports");
  await expect(page.getByRole("heading", { level: 3, name: "Forecast by intake" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
});
