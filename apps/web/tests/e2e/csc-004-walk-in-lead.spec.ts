import { test, expect, type Page } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// csc-004 (DEC-SCOPE-229) -- an overseas counselor records a walk-in as a lead from My leads: the source is preset to Walk-in, there is no
// Division picker, the lead opens as the counselor's, and entering the same mobile again shows the duplicate panel. Requires the stack
// running with `python -m app.seed` applied (Overseas products from migration 0076, an Overseas telecaller from the seed).

const mobile = () => `9${String(Date.now()).slice(-9)}`;

async function openNewWalkInLead(page: Page) {
  await page.goto("/overseas/counselor/leads");
  await page.getByRole("link", { name: "New walk-in lead" }).click();
  await expect(page.getByRole("heading", { name: "New walk-in lead" })).toBeVisible();
}

async function fill(page: Page, name: string, phone: string) {
  await page.getByLabel(/Student name/).fill(name);
  await page.getByLabel(/Mobile number/).fill(phone);
  const product = page.getByLabel(/Product interest/);
  await expect(product.locator("option").nth(1)).toBeAttached();
  await product.selectOption({ index: 1 });
}

test("a counselor records a walk-in lead that opens as theirs, and a repeat is caught as a duplicate (csc-004)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && !m.text().includes("status of 409") && consoleErrors.push(m.text()));
  await signInAsFreshCounselor(page, "csc004");
  await openNewWalkInLead(page);
  await expect(page.getByLabel(/Lead source/)).toHaveValue("walk_in");
  await expect(page.getByLabel(/Division/)).toHaveCount(0);

  const phone = mobile();
  const name = `Walk-in Lead ${Date.now()}`;
  await fill(page, name, phone);
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/overseas\/counselor\/leads\/[0-9a-f-]{36}$/);
  await expect(page.getByText(name).first()).toBeVisible();

  await page.goto("/overseas/counselor/leads");
  await expect(page.getByRole("row").filter({ hasText: name })).toBeVisible();

  await openNewWalkInLead(page);
  await fill(page, "Same Person Again", phone);
  await page.getByRole("button", { name: "Create lead" }).click();
  await expect(page.getByRole("heading", { name: /Lead already exists/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Open LD-/ })).toBeVisible(); // in scope: it is this counselor's own lead
  expect(consoleErrors).toEqual([]);
});

test("the walk-in form fits a phone screen (csc-004)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signInAsFreshCounselor(page, "csc004");
  await openNewWalkInLead(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
