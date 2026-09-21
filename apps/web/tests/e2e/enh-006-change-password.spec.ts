import { test, expect, type Page } from "@playwright/test";

// ENH-006 -- self-service change password (DEC-SCOPE-021). Requires the stack running via `docker compose up` with the
// api and web images rebuilt after this change. Every test registers its own throwaway student and never changes a
// seeded account's password (other specs sign in with it).

const OLD_PASSWORD = "Sup3r-Secret-Pass!";
const NEW_PASSWORD = "Brand-New-Pass-1!";

async function registerStudent(page: Page) {
  const email = `enh006-e2e-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}@example.local`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email, password: OLD_PASSWORD, full_name: "E2E Change Password", division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  return email; // registering also signed this browser context in
}

async function fillAndSubmit(page: Page, current: string, next: string) {
  await page.getByLabel("Current password").fill(current);
  await page.getByLabel("New password").fill(next);
  await page.getByRole("button", { name: "Change password" }).click();
}

const login = (page: Page, email: string, password: string) => page.request.post("/api/v1/auth/login", { data: { email, password, division: "it" } });

test("a signed-in user changes their password through the page and only the new one signs in (ENH-006)", async ({ page }) => {
  const email = await registerStudent(page);
  await page.goto("/account/password");
  await expect(page.getByRole("heading", { name: "Change your password" })).toBeVisible();
  await fillAndSubmit(page, OLD_PASSWORD, NEW_PASSWORD);
  await expect(page.locator(".form-message")).toHaveText("Your password was changed.");
  await page.request.post("/api/v1/auth/logout");
  expect((await login(page, email, OLD_PASSWORD)).status()).toBe(401);
  expect((await login(page, email, NEW_PASSWORD)).status()).toBe(200);
});

test("the form can be completed and submitted from the keyboard (ENH-006 accessibility)", async ({ page }) => {
  const email = await registerStudent(page);
  await page.goto("/account/password");
  await page.getByLabel("Current password").focus();
  await page.keyboard.type(OLD_PASSWORD);
  await page.keyboard.press("Tab");
  await page.keyboard.type(NEW_PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page.locator(".form-message")).toHaveText("Your password was changed.");
  await expect(page.getByRole("button", { name: "Change password" })).toBeFocused();
  await page.request.post("/api/v1/auth/logout");
  expect((await login(page, email, NEW_PASSWORD)).status()).toBe(200);
});

test("a wrong current password shows the generic error, clears and refocuses that field, and offers recovery (ENH-006)", async ({ page }) => {
  const email = await registerStudent(page);
  await page.goto("/account/password");
  await fillAndSubmit(page, "not-the-password", NEW_PASSWORD);
  await expect(page.locator(".form-error")).toContainText("Incorrect current password");
  await expect(page.getByLabel("Current password")).toHaveValue("");
  await expect(page.getByLabel("Current password")).toBeFocused();
  await expect(page.getByLabel("New password")).toHaveValue(NEW_PASSWORD);
  await expect(page.getByRole("link", { name: "Forgot your current password?" })).toHaveAttribute("href", "/it/forgot-password");
  await expect(page.locator(".form-message")).toHaveCount(0);
  expect((await login(page, email, OLD_PASSWORD)).status()).toBe(200);
});

test("after five wrong attempts the page shows the rate-limit message, even for the right password (ENH-006)", async ({ page }) => {
  const email = await registerStudent(page);
  for (let i = 0; i < 5; i++) {
    const wrong = await page.request.post("/api/v1/auth/change-password", { data: { current_password: "not-the-password", new_password: NEW_PASSWORD } });
    expect(wrong.status()).toBe(400);
  }
  await page.goto("/account/password");
  await fillAndSubmit(page, OLD_PASSWORD, NEW_PASSWORD);
  await expect(page.locator(".form-error")).toContainText("Too many incorrect attempts");
  expect((await login(page, email, OLD_PASSWORD)).status()).toBe(200); // the password was not changed
});

test("Show passwords reveals both fields and hides them again (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  await expect(page.getByLabel("New password")).toHaveAttribute("type", "password");
  await page.getByLabel("Show passwords").check();
  await expect(page.getByLabel("Current password")).toHaveAttribute("type", "text");
  await expect(page.getByLabel("New password")).toHaveAttribute("type", "text");
  await page.getByLabel("Show passwords").uncheck();
  await expect(page.getByLabel("New password")).toHaveAttribute("type", "password");
});

test("a signed-out visitor is sent to sign in and lands back on the password page (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/account/password");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
  await page.getByRole("link", { name: "IT Training sign in" }).click();
  await page.waitForURL("**/it/login**");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/account/password");
  await expect(page.getByRole("heading", { name: "Change your password" })).toBeVisible();
});

test("the Password link is reachable from the signed-in public header (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/it");
  await page.getByRole("link", { name: "Password", exact: true }).click();
  await page.waitForURL("**/account/password");
  await expect(page.getByRole("heading", { name: "Change your password" })).toBeVisible();
});

test("a portal user reaches the page from the sidebar and can go back to their dashboard (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/it/student/dashboard");
  await page.locator(".sidebar-footer").getByRole("link", { name: "Change password" }).click();
  await page.waitForURL("**/account/password");
  await page.getByRole("link", { name: "← Back to dashboard" }).click();
  await page.waitForURL("**/it/student/dashboard");
});

test("on a 375px phone the portal menu leads to a usable page with no horizontal scroll (ENH-006 mobile)", async ({ page }) => {
  await registerStudent(page);
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/it/student/dashboard");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.locator("#portal-mobile-nav-panel").getByRole("link", { name: "Change password" }).click();
  await page.waitForURL("**/account/password");
  await expect(page.getByLabel("Current password")).toBeVisible();
  await expect(page.getByLabel("New password")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const button = page.getByRole("button", { name: "Change password" });
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44); // touch target
  await fillAndSubmit(page, OLD_PASSWORD, NEW_PASSWORD);
  await expect(page.locator(".form-message")).toHaveText("Your password was changed.");
});
