import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-015 (§32 "Alerts", AL12-AL14): the manager reaches Alerts from the sidebar, switches kinds (each with its own empty text, in the URL),
// the head has the same entry, another staff role is refused, and the page fits a phone. The alerts themselves are raised by the beat
// (covered by test_upc_015_alerts.py); throwaway accounts via the real admin API start with none.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const send = async (data: unknown) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await send({ role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc015-h-${stamp}@example.local` });
  const manager = await send({
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc015-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U15-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await send({ role: "overseas_admin", division: "overseas", full_name: `E2E Admin ${stamp}`, email: `upc015-a-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, admin };
}

test("a manager opens Alerts from the sidebar and switches kinds; the head has it too; another role is refused", async ({ page }) => {
  const { head, manager, admin } = await setUp(page, Date.now());

  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.locator(".portal-nav").getByRole("link", { name: "Alerts" }).click();
  await page.waitForURL("**/partnership/alerts");
  await expect(page.getByRole("heading", { name: "Alerts", level: 2 })).toBeVisible();
  await expect(page.getByRole("link", { name: "All alerts" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(/^No alerts yet\./)).toBeVisible();

  await page.getByRole("link", { name: "Delayed milestones" }).click();
  await page.waitForURL("**/partnership/alerts?kind=milestone_delayed");
  await expect(page.getByRole("link", { name: "Delayed milestones" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(/^No delayed milestones\./)).toBeVisible();

  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/partnership/alerts?kind=agreement_expiry");
  await expect(page.getByText(/^No agreement expiry alerts\./)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.locator(".portal-nav").getByRole("link", { name: "Alerts" }).click();
  await page.waitForURL("**/partnership/alerts");
  await expect(page.getByText(/^No alerts yet\./)).toBeVisible();

  await signIn(page, "/overseas/login", admin.email, "/overseas/admin/dashboard");
  await page.goto("/partnership/alerts");
  await expect(page.getByText("Partnership alerts access required")).toBeVisible();
});
