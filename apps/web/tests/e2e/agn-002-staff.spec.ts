import { test, expect, type Browser } from "@playwright/test";

import { E2E_PASSWORD } from "./helpers/welcome";
import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-002 -- a Master adds staff; staff work on students without Team/Commissions; deactivate signs them out; reactivate; reset.
// Requires the stack running with `python -m app.seed` applied. The staff-create response never carries the link token (S3), so
// the spec activates the account the way an admin would re-send it (the admin Re-send response carries it in dev/test).

async function staffPage(browser: Browser) {
  const context = await browser.newContext();
  return context.newPage();
}

test("a Master adds staff who work on students; deactivate, reactivate and reset (AGN-002)", async ({ page, browser }) => {
  test.setTimeout(180_000); // includes the 60 s reset cooldown
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique);
  const staffEmail = `agn002-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  await expect(page.getByText("No staff yet. Add your first staff member below.")).toBeVisible();
  const form = page.getByRole("form", { name: "Add a staff member" });
  await form.getByLabel("Full name").fill("Sigma Staff");
  await form.getByLabel("Email").fill(staffEmail);
  await form.getByRole("button", { name: "Add staff" }).click();
  await expect(page.getByText(/SIG\d*-S001 created/)).toBeVisible();
  await expect(page.getByText("Set-up pending")).toBeVisible();

  const staff = await staffPage(browser);
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await expect(staff.getByRole("link", { name: "Students" }).first()).toBeVisible();
  await expect(staff.getByRole("link", { name: "Team", exact: true })).toHaveCount(0);
  await expect(staff.getByRole("link", { name: "Commissions", exact: true })).toHaveCount(0);
  await staff.goto("/overseas/agent/team");
  await expect(staff.getByText("Only an agency Master can open this page")).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Deactivate Sigma Staff" }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByText(/deactivated\. They have been signed out\./)).toBeVisible();
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  await page.getByRole("button", { name: "Reactivate Sigma Staff" }).click();
  await expect(page.getByText(/reactivated\./)).toBeVisible();
  await signIn(staff, staffEmail, E2E_PASSWORD);

  // The activation link above was issued seconds ago, so the per-account 60 s cooldown (spec E7) refuses the first reset and
  // says so on the row; the confirmation stays open and the reset goes through once the cooldown has passed.
  await page.getByRole("button", { name: "Reset Sigma Staff" }).click();
  await page.getByRole("button", { name: "Confirm reset" }).click();
  await expect(page.getByText(/A link was just sent; wait \d+ seconds before resetting again/)).toBeVisible();
  await page.waitForTimeout(61_000);
  await page.getByRole("button", { name: "Confirm reset" }).click();
  await expect(page.getByText(/set-password link was emailed|login was reset/)).toBeVisible();
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await staff.goto("/overseas/login");
  await staff.fill("#login-email", staffEmail);
  await staff.fill("#login-password", E2E_PASSWORD);
  await staff.click("button:has-text('Sign in securely')");
  await expect(staff).toHaveURL(/\/overseas\/login/);
  await staff.context().close();
});
