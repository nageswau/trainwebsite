import { test, expect, type Page } from "@playwright/test";

// AGN-001 -- agency registration -> approval -> Master invite -> suspend -> reinstate, through the real UI.
// Requires the stack running with `python -m app.seed` applied (seeds the overseas admin).

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function adminAct(page: Page, agency: string, button: string) {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  // The panel shows one status tab at a time (Pending first); open the tab the organisation is on.
  const tabs: Record<string, string> = { Suspend: "Approved", Reinstate: "Suspended" };
  if (tabs[button]) await page.getByRole("button", { name: tabs[button], exact: true }).click();
  const card = page.locator(".card", { hasText: agency });
  await card.getByRole("button", { name: button }).click();
  if (button === "Suspend") await card.getByRole("button", { name: "Confirm suspend" }).click();
}

test("an agency registers, is approved, invites a second Master, and is suspended then reinstated (AGN-001)", async ({ page }) => {
  const unique = Date.now();
  const agency = `Kappa Overseas ${unique}`;
  const email = `agn001-e2e-${unique}@example.local`;

  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Kappa Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await expect(page.getByText(/pending approval/)).toBeVisible();

  await adminAct(page, agency, "Approve");
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();

  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByText(/KAP\d*-M001/)).toBeVisible();
  await page.goto("/overseas/agent/team");
  await page.getByLabel("Full name").fill("Kappa Second");
  await page.getByLabel("Email").fill(`agn001-e2e-m2-${unique}@example.local`);
  await page.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText(/KAP\d*-M002/).first()).toBeVisible();
  await expect(page.getByText("Invite pending").first()).toBeVisible();

  await adminAct(page, agency, "Suspend");
  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByText("Your agency's account is suspended")).toBeVisible();

  await adminAct(page, agency, "Reinstate");
  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).not.toBeVisible();
});
