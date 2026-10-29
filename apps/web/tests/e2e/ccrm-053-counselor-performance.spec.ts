import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-053 (DEC-SCOPE-325, PF1-PF10): the counselor's Overseas/IT lead split and intake / division filters, and the Overseas Admin's
// counselor performance list, its export and each counselor's report. Seeded demo accounts; the shared stack DB also holds backend-test
// rows, so the checks are relational (split sums, CSV = screen, row = report), never fixed numbers.

const COUNSELOR = ["counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard"] as const;
const ADMIN = ["overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard"] as const;
const API = "/api/v1/overseas-admin/counselor-performance";

type Row = { id: string; full_name: string; leads: number; leads_overseas: number; leads_it: number; applications: number };

test("the counselor filters their report by intake and lead division, and the address keeps both", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signIn(page, ...COUNSELOR);
  await page.goto("/overseas/counselor/reports");
  const period = page.getByRole("list", { name: "In the period" });
  for (const label of ["Leads", "Overseas leads", "IT leads"]) await expect(period.getByText(label, { exact: true })).toBeVisible();

  await page.getByLabel("Intake month").selectOption("Sep");
  await page.getByLabel("Intake year").selectOption("2027");
  await page.getByLabel("Lead division").selectOption("it");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/intake=Sep\+2027&division=it/);
  await expect(page.getByText(/Leads for the Sep 2027 intake in the IT division only\./)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Intake month")).toHaveValue("Sep");
  await expect(page.getByLabel("Lead division")).toHaveValue("it");

  // "All divisions" sends an empty value, which the page drops from the address
  await page.getByLabel("Lead division").selectOption("");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/intake=Sep\+2027$/);

  await page.goto("/overseas/counselor/reports?intake=Autumn");
  await expect(page.locator(".form-error")).toHaveText("Choose the intake month and year, like Sep 2027");
  await expect(page.getByLabel("Intake month")).toBeVisible();
  expect(errors).toEqual([]);
});

test("the counselor is refused the Overseas Admin's page and routes", async ({ page }) => {
  await signIn(page, ...COUNSELOR);
  await page.goto("/overseas/admin/counselor-performance");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  expect((await page.request.get(API)).status()).toBe(403);
  expect((await page.request.get(`${API}.csv`)).status()).toBe(403);
});

test("the Overseas Admin compares every overseas counselor, exports the screen and opens one counselor", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signIn(page, ...ADMIN);
  await page.getByRole("link", { name: "Counselor performance", exact: true }).click();
  await expect(page).toHaveURL(/\/overseas\/admin\/counselor-performance$/);
  await expect(page.getByRole("heading", { name: "Counselor performance", level: 2 })).toBeVisible();
  const region = page.getByRole("region", { name: "Overseas counselors" });
  await expect(region.getByRole("columnheader", { name: "IT leads" })).toBeVisible();
  await expect(page.getByText(/revenue/i)).toHaveCount(0);

  // AC3 on every row, AC6: the CSV is the screen
  const body = await (await page.request.get(API)).json();
  const items: Row[] = body.items;
  expect(items.length).toBeGreaterThan(0);
  for (const r of items) expect(r.leads_overseas + r.leads_it).toBe(r.leads);
  await expect(region.locator("tbody tr")).toHaveCount(items.length);
  const csv = await page.request.get(`${API}.csv`);
  expect(csv.status()).toBe(200);
  const lines = (await csv.text()).replace(/^﻿/, "").trim().split(/\r?\n/);
  expect(lines[0].split(",")).toEqual(body.columns.map((c: { label: string }) => c.label));
  expect(lines).toHaveLength(items.length + 2);
  await expect(page.getByRole("group", { name: "Export counselor performance" }).getByRole("button", { name: "Download CSV" })).toBeVisible();

  // a counselor's row opens their report with the same figures
  const demo = items.find((r) => r.full_name.includes("Counselor")) ?? items[0];
  await page.getByLabel("Intake month").selectOption("Sep");
  await page.getByLabel("Intake year").selectOption("2027");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/intake=Sep\+2027/);
  await region.getByRole("link", { name: demo.full_name, exact: true }).first().click();
  await expect(page).toHaveURL(new RegExp(`/overseas/admin/counselor-performance/${demo.id}\\?.*intake=Sep\\+2027`));
  await expect(page.getByRole("heading", { level: 2 })).toContainText(demo.full_name);
  const filtered: Row = (await (await page.request.get(`${API}?intake=Sep+2027`)).json()).items.find((r: Row) => r.id === demo.id);
  const tile = page.getByRole("list", { name: "In the period" }).getByText("Leads", { exact: true }).locator("..");
  await expect(tile.locator("strong")).toHaveText(filtered.leads.toLocaleString("en-IN"));
  await page.getByRole("link", { name: "Back to all counselors" }).click();
  await expect(page).toHaveURL(/\/overseas\/admin\/counselor-performance\?.*intake=Sep\+2027/);

  await page.goto("/overseas/admin/counselor-performance/00000000-0000-0000-0000-000000000000");
  await expect(page.locator(".form-error")).toContainText("This counselor was not found.");
  expect(errors).toEqual([]);
});

for (const [name, width] of [["phone", 375], ["tablet", 768], ["desktop", 1280]] as const) {
  test(`the Overseas Admin's page fits a ${name} without sideways page scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page, ...ADMIN);
    await page.goto("/overseas/admin/counselor-performance");
    await expect(page.getByRole("region", { name: "Overseas counselors" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}
