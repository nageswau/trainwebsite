import { expect, test } from "@playwright/test";

import { KYC_PDF, fillAgentKyc, signIn } from "./helpers/agency";

// AGN-024 (DEC-SCOPE-224): signup with three documents -> admin rejects Aadhaar -> agent re-uploads -> admin verifies all ->
// Approve enabled -> agent reaches the dashboard. A Super Admin variant covers K7; a 360 px check covers the signup form.

test("agent KYC journey: reject, re-upload, verify all, approve (AGN-024)", async ({ page }) => {
  const unique = Date.now();
  const email = `agn024-${unique}@example.local`;
  const agency = `KYC Agency ${unique}`;
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "KYC Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await fillAgentKyc(page);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/registration-status");
  await expect(page.getByText("Pending review")).toHaveCount(3);

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/agents?q=${encodeURIComponent(agency)}`);
  const card = page.locator(".card", { hasText: agency });
  await expect(card.getByRole("button", { name: `Approve ${agency}` })).toBeDisabled();
  await card.getByRole("button", { name: `Reject Aadhaar card for ${agency}` }).click();
  await card.getByLabel("Reason for rejecting Aadhaar card").fill("Photo is blurred");
  await card.getByRole("button", { name: "Confirm reject" }).click();
  await expect(card.getByText("Reason: Photo is blurred")).toBeVisible();

  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard").catch(() => undefined);  // a pending agent lands on the access card
  await page.goto("/overseas/agent/registration-status");
  await expect(page.getByText("Reason: Photo is blurred")).toBeVisible();
  await page.getByLabel(/^New Aadhaar card file/).setInputFiles(KYC_PDF);
  await page.getByRole("button", { name: "Upload new Aadhaar card" }).click();
  await expect(page.getByText("Aadhaar card uploaded. It will be reviewed again.")).toBeVisible();

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/agents?q=${encodeURIComponent(agency)}`);
  for (const label of ["PAN card", "Aadhaar card", "Business licence"]) {
    await card.getByRole("button", { name: `Verify ${label} for ${agency}` }).click();
    await expect(card.getByText(`${label} verified.`)).toBeVisible();
  }
  await expect(card.getByRole("button", { name: `Approve ${agency}` })).toBeEnabled();
  await card.getByRole("button", { name: `Approve ${agency}` }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();

  await signIn(page, email, "Sup3r-Secret-Pass!");
  await expect(page).toHaveURL(/\/overseas\/agent\/dashboard/);
});

test("Super Admin sees Agent Approvals with the document review (AGN-024 K7)", async ({ page }) => {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  await page.getByRole("link", { name: "Agent Approvals" }).click();
  await expect(page.getByRole("heading", { name: "Agent Approvals" })).toBeVisible();
});

test("signup form with documents fits a 360 px screen (AGN-024)", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/overseas/register");
  await page.selectOption('select[name="account_type"]', "agent");
  await expect(page.getByLabel(/^PAN card/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
