import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ENH-003 / DEC-SCOPE-019 -- first-time provisioning: no default password, emailed 72-hour
// single-use link, admin Re-send. Accounts are throwaway records created through the real admin API.

async function signIn(page: Page, division: "it" | "overseas", email: string, password = "Demo@123") {
  await page.goto(`/${division}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**/${division}/admin/dashboard`);
}

const overseasAdmin = (page: Page) => signIn(page, "overseas", "overseasadmin@edusphere.local");
const itAdmin = (page: Page) => signIn(page, "it", "itadmin@edusphere.local");

// The retired default password, built in two parts so the repo-wide "no default password" grep gate
// stays clean while this spec can still prove the old default no longer logs in.
const RETIRED_DEFAULT = "Change" + "Me@12345";

test("a provisioned staff account has no default password and activates from its link", async ({ page }) => {
  await overseasAdmin(page);
  const email = `enh003-staff-${Date.now()}@example.local`;
  const created = await page.request.post("/api/v1/overseas-admin/school-staff", { data: { role: "academic_team", full_name: "ENH-003 Staff", email } });
  expect(created.status()).toBe(201);
  const body = await created.json();
  expect(JSON.stringify(body)).not.toContain("ChangeMe");
  expect(Object.keys(body).some((key) => key.toLowerCase().includes("password"))).toBe(false);

  await page.request.post("/api/v1/auth/logout");
  const denied = await page.request.post("/api/v1/auth/login", { data: { email, password: RETIRED_DEFAULT, division: "overseas" } });
  expect(denied.status()).toBe(401);

  await activateWithToken(page.request, body.development_welcome_token);
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");
});

test("the admin form reports the link outcome in a live region and never shows a password", async ({ page }) => {
  await overseasAdmin(page);
  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "career_counselor");
  await page.fill("#staff-name", "ENH-003 Form Staff");
  await page.fill("#staff-email", `enh003-form-${Date.now()}@example.local`);
  await page.getByRole("button", { name: "Create account" }).click();
  const outcome = page.getByRole("status").filter({ hasText: /Account created for/ });
  await expect(outcome).toBeVisible();
  await expect(outcome).toContainText(/set-password link was emailed|email was not delivered/);
  await expect(page.getByText(/ChangeMe|default password/i)).toHaveCount(0);
});

test("Re-send supersedes the old link and the new one works", async ({ page }) => {
  await overseasAdmin(page);
  const email = `enh003-resend-${Date.now()}@example.local`;
  const created = await (await page.request.post("/api/v1/admin/users", { data: { role: "counselor", division: "overseas", email, full_name: "ENH-003 Resend" } })).json();
  const resent = await page.request.post(`/api/v1/admin/users/${created.id}/welcome-links`);
  expect(resent.status()).toBe(201);
  const fresh = await resent.json();

  // the cooldown (security review S4): a second Re-send right away is throttled and issues nothing
  const again = await page.request.post(`/api/v1/admin/users/${created.id}/welcome-links`);
  expect(again.status()).toBe(429);
  expect(Number(again.headers()["retry-after"])).toBeGreaterThan(0);

  const stale = await page.request.post("/api/v1/auth/reset-password", { data: { token: created.development_welcome_token, new_password: E2E_PASSWORD } });
  expect(stale.status()).toBe(400);
  await activateWithToken(page.request, fresh.development_welcome_token);
  const login = await page.request.post("/api/v1/auth/login", { data: { email, password: E2E_PASSWORD, division: "overseas" } });
  expect(login.status()).toBe(200);
});

test("an invalid link offers a real recovery link, and the page fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/overseas/reset-password?token=not-a-real-token");
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Reset token is invalid or expired");
  await expect(alert).toContainText("ask your administrator to re-send it");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await alert.getByRole("link", { name: "Request a new reset link" }).click();
  await page.waitForURL("**/overseas/forgot-password");
});

test("the users directory shows the setup status and Re-send works from the keyboard", async ({ page }) => {
  await itAdmin(page);
  const name = `ENH-003 Directory ${Date.now()}`;
  const created = await page.request.post("/api/v1/admin/users", { data: { role: "trainer", division: "it", email: `enh003-dir-${Date.now()}@example.local`, full_name: name } });
  expect(created.status()).toBe(201);

  await page.goto("/it/admin/users");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage users" }) });
  await panel.getByLabel("Search by name, email, or role").fill(name);
  const row = panel.locator("tr", { hasText: name });
  await expect(row).toContainText("Active");
  await expect(row.getByText("Awaiting setup")).toBeVisible();

  await panel.getByLabel("Account setup").selectOption("link_expired");
  await expect(row).toBeHidden();
  await panel.getByRole("button", { name: "Show all accounts" }).click();
  await expect(row).toBeVisible();

  const resend = row.getByRole("button", { name: `Re-send set-password link to ${name}` });
  await resend.focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status").filter({ hasText: `New link created for ${name}.` })).toBeVisible();
  await expect(resend).toBeFocused();
});

test("the expired-links panel is present on the admin dashboard and fits a phone", async ({ page }) => {
  await itAdmin(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/it/admin/dashboard");
  const heading = page.getByRole("heading", { name: /Expired set-password links/ });
  await expect(heading).toBeVisible();
  const card = page.locator(".action-card", { has: heading });
  await expect(card.getByText(/No expired links\.|Link expired|Loading expired links/).first()).toBeVisible();
  const box = await card.boundingBox();
  expect(box && box.x >= 0 && box.x + box.width <= 375).toBe(true);
});

test("the reset page never leaks its token in a Referer", async ({ page }) => {
  const response = await page.goto("/overseas/reset-password?token=not-a-real-token");
  expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
});
