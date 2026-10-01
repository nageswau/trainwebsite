import { test, expect } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-021 -- a Master opens a staff member's Activity on the Team page; work the staff member does shows on the next load
// (Refresh, or reopening). Requires the stack running with `python -m app.seed` applied.

test("a staff member's work appears in the Master's activity view on the next load (AGN-021)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn021");
  const staffEmail = `agn021-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  const created = await page.request.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "Upsilon Staff", email: staffEmail } });
  expect(created.status()).toBe(201);

  await page.goto("/overseas/agent/team");
  await page.getByRole("button", { name: "Activity of Upsilon Staff" }).click();
  await expect(page.getByText("No activity yet.")).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  const record = await staff.request.post("/api/v1/workflows/overseas/agent/crm/students", { data: { full_name: `Phi Student ${unique}` } });
  expect(record.status()).toBe(201);

  await page.getByRole("button", { name: "Refresh" }).click();
  const list = page.getByRole("list", { name: /^Activity of / });
  await expect(list.getByText("Created a student record")).toBeVisible();
  await expect(list.getByText(`Phi Student ${unique}`)).toBeVisible();

  await page.getByRole("button", { name: "Close activity" }).click();
  await expect(page.getByRole("button", { name: "Activity of Upsilon Staff" })).toBeFocused();
});

test("the activity view fits a 320 px screen (AGN-021)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await page.goto("/overseas/agent/team");
  const activity = page.getByRole("button", { name: /^Activity of / }).first();
  if (await activity.count()) {
    await activity.click();
    await expect(page.getByRole("region", { name: "Activity" })).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
