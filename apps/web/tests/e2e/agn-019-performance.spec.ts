import { test, expect, type Browser } from "@playwright/test";

import { E2E_PASSWORD } from "./helpers/welcome";
import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-019 (DEC-SCOPE-063) -- the Master-only Staff Performance page. Requires the stack running with `python -m app.seed` applied
// (the AGN-002 flow creates the staff member). Run in the browser-validation phase.

async function newPage(browser: Browser) {
  return (await browser.newContext()).newPage();
}

test("a Master filters staff performance and switches the funnel; staff never see it (AGN-019)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique);
  const staffEmail = `agn019-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  const form = page.getByRole("form", { name: "Add a staff member" });
  await form.getByLabel("Full name").fill("Sigma Staff");
  await form.getByLabel("Email").fill(staffEmail);
  await form.getByRole("button", { name: "Add staff" }).click();
  await expect(page.getByText(/-S001 created/)).toBeVisible();

  // The dashboard summary links to the page; the sidebar has it too.
  await page.goto("/overseas/agent/dashboard");
  await page.getByRole("link", { name: "View staff performance" }).click();
  await expect(page).toHaveURL(/\/overseas\/agent\/performance$/);
  await expect(page.locator(".portal-nav").getByRole("link", { name: "Staff Performance", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Staff performance" })).toBeVisible();
  await expect(page.getByText("Your agency has no students yet.")).toBeVisible();
  await expect(page.getByRole("region", { name: "By staff member" })).toContainText("Sigma Staff");

  // A student, then the funnel for the agency and for the staff member.
  await page.goto("/overseas/agent/students?new=1");
  const add = page.getByRole("form", { name: "Add student" });
  await add.getByLabel(/Full name/).fill(`Funnel Student ${unique}`);
  await add.getByRole("button", { name: "Save student" }).click();
  await expect(add).toHaveCount(0);
  await page.goto("/overseas/agent/performance");
  const funnel = page.getByRole("list", { name: /^Student funnel/ });
  await expect(funnel.getByRole("listitem").first()).toContainText("Students1100% of students");
  await page.getByLabel("Show funnel for").selectOption({ label: "Unassigned" });
  await expect(page.getByRole("list", { name: "Student funnel: Unassigned" })).toBeVisible();

  // The range: keyboard only, kept in the address; a range before any student is empty.
  await page.getByLabel("From").fill("2020-01-01");
  await page.getByLabel("To").fill("2020-01-31");
  await page.getByLabel("To").press("Enter");
  await expect(page.getByText("No students were added in this period.")).toBeVisible();
  await expect.poll(() => new URL(page.url()).search).toBe("?from=2020-01-01&to=2020-01-31");
  await page.reload();
  await expect(page.getByLabel("From")).toHaveValue("2020-01-01");

  // Staff: no nav item; the address shows the Masters-only note; the API refuses them.
  const staff = await newPage(browser);
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/dashboard");
  await expect(staff.locator(".portal-nav").getByRole("link", { name: "Staff Performance" })).toHaveCount(0);
  await staff.goto("/overseas/agent/performance");
  await expect(staff.getByText("Staff performance is available to agency Masters.")).toBeVisible();
  expect((await staff.request.get("/api/v1/workflows/overseas/agent/crm/performance")).status()).toBe(403);
});

test("the page fits a 320 px screen with no horizontal scroll (AGN-019)", async ({ page }) => {
  const masterEmail = await registerApprovedAgency(page, Date.now());
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/performance");
  await expect(page.getByRole("form", { name: "Staff performance filters" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});
