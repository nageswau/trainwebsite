import { test, expect } from "@playwright/test";

// AUTH-001 -- Division-aware authenticated login. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (demo password
// Demo@123, see apps/web/app/it/login/page.tsx for the account list).

test("login succeeds and redirects to the role's dashboard (AUTH-001-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
  await expect(page).toHaveURL(/\/it\/student\/dashboard/);
});

test("invalid credentials show a generic error, no user enumeration (AUTH-001-AC03)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "wrong-password-xyz");
  await page.click("button:has-text('Sign in securely')");
  const wrongPasswordError = await page.locator(".form-error").innerText();

  await page.fill("#login-email", "no-such-user@example.local");
  await page.fill("#login-password", "wrong-password-xyz");
  await page.click("button:has-text('Sign in securely')");
  const unknownUserError = await page.locator(".form-error").innerText();

  expect(wrongPasswordError).toBe(unknownUserError);
  await expect(page).toHaveURL(/\/it\/login/);
});

test("wrong-division login is rejected, not silently accepted (FND-002)", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await expect(page.locator(".form-error")).toBeVisible();
  await expect(page).toHaveURL(/\/overseas\/login/);
});

test("forgot-password returns an identical response whether or not the account exists (AUTH-001-AC02)", async ({ page }) => {
  await page.goto("/it/forgot-password");
  await page.fill("#forgot-email", "student.it@edusphere.local");
  await page.click("button:has-text('Send reset instructions')");
  const existingMessage = await page.locator("[role='status']").innerText();

  await page.goto("/it/forgot-password");
  await page.fill("#forgot-email", "no-such-user@example.local");
  await page.click("button:has-text('Send reset instructions')");
  const unknownMessage = await page.locator("[role='status']").innerText();

  expect(existingMessage).toBe(unknownMessage);
});

test("unauthenticated access to a protected route redirects to login (FND-002)", async ({ page }) => {
  await page.goto("/it/student/dashboard");
  await expect(page).toHaveURL(/\/it\/login/);
});

test("login form has associated labels for both fields (accessibility)", async ({ page }) => {
  await page.goto("/it/login");
  await expect(page.locator("label[for='login-email']")).toHaveCount(1);
  await expect(page.locator("label[for='login-password']")).toHaveCount(1);
});

test("login form is usable at a 375px mobile viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/it/login");
  await expect(page.locator("#login-email")).toBeVisible();
  await expect(page.locator("button:has-text('Sign in securely')")).toBeVisible();
});
