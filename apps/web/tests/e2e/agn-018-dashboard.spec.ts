import { test, expect, type Browser } from "@playwright/test";

import { E2E_PASSWORD } from "./helpers/welcome";
import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-018 (DEC-SCOPE-060) -- the agency Master / Staff dashboards and the staff sidebar. Requires the stack running with
// `python -m app.seed` applied (the AGN-002 flow creates the staff member). Run in the browser-validation phase.

async function newPage(browser: Browser) {
  return (await browser.newContext()).newPage();
}

test("a Master sees the agency board; staff see their own board and the §4 sidebar (AGN-018)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique);
  const staffEmail = `agn018-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/dashboard");
  for (const heading of ["Students", "Pipeline", "Documents", "Commission", "Staff performance"]) {
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
  await expect(page.getByText(/Whole agency/)).toBeVisible();
  await expect(page.getByText("Revenue", { exact: true })).toBeVisible();
  await expect(page.getByText("No staff yet — add staff from Team")).toBeVisible();

  await page.goto("/overseas/agent/team");
  const form = page.getByRole("form", { name: "Add a staff member" });
  await form.getByLabel("Full name").fill("Omega Staff");
  await form.getByLabel("Email").fill(staffEmail);
  await form.getByRole("button", { name: "Add staff" }).click();
  await expect(page.getByText(/-S001 created/)).toBeVisible();
  await page.goto("/overseas/agent/dashboard");
  await expect(page.getByRole("region", { name: "Staff performance" })).toContainText("Omega Staff");

  const staff = await newPage(browser);
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/dashboard");
  await expect(staff.getByText(/Your assigned students/)).toBeVisible();
  await expect(staff.getByText(/commission/i)).toHaveCount(0);
  await expect(staff.getByRole("region", { name: "Staff performance" })).toHaveCount(0);

  const nav = staff.locator(".portal-nav");
  await expect(nav.getByRole("link", { name: "My Students", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Tasks & Follow-ups", exact: true })).toBeVisible();
  await nav.getByRole("link", { name: "Add", exact: true }).click();
  const add = staff.getByRole("form", { name: "Add student" });
  await expect(add).toBeVisible();
  await expect(add.getByLabel(/Full name/)).toBeFocused();
  await expect.poll(() => new URL(staff.url()).search).toBe("");
});

test("the board fits a 320 px screen: empty agency notes, and the seeded agency's tables show every number (AGN-018)", async ({ page }) => {
  const masterEmail = await registerApprovedAgency(page, Date.now());
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/dashboard");
  await expect(page.getByRole("heading", { name: "Pipeline", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  // QA18-05: an agency with no staff gets the note, not a header-only table.
  await expect(page.getByText("No staff yet — add staff from Team")).toBeVisible();
  await expect(page.getByRole("region", { name: "Staff performance" })).toHaveCount(0);

  // The seeded agency (python -m app.seed) has applications: its tables are keyboard regions and no number is cut off (QA18-04).
  await signIn(page, "agent@edusphere.local", "Demo@123");
  const region = page.getByRole("region", { name: "Applications by country" });
  await region.focus();
  await expect(region).toBeFocused();
  const hidden = await page.evaluate(() =>
    [...document.querySelectorAll(".table-scroll td")].filter((td) => td.getBoundingClientRect().right > document.documentElement.clientWidth).length,
  );
  expect(hidden).toBe(0);
});
