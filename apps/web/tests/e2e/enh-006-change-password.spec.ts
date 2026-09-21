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
  const menuLink = page.locator("#portal-mobile-nav-panel").getByRole("link", { name: "Change password" });
  const menuBox = (await menuLink.boundingBox())!;
  expect(menuBox.y + menuBox.height, "Change password is visible without scrolling the menu (QA-004)").toBeLessThanOrEqual(667);
  await menuLink.click();
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

// ---- Browser QA follow-ups (docs/quality/ENH-006_BROWSER_QA_2026-09-21.md). Each was written and seen failing first.

test("the signed-in public header fits the viewport and Logout stays reachable at laptop and tablet widths (QA-001)", async ({ page }) => {
  await registerStudent(page);
  for (const width of [1600, 1440, 1366, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/it");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
    const logout = (await page.getByRole("button", { name: "Logout" }).boundingBox())!;
    expect(logout.x + logout.width, `Logout's right edge at ${width}px`).toBeLessThanOrEqual(width);
  }
});

test("the page has its own title (QA-005)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  await expect(page).toHaveTitle("Change your password | EduSphere");
});

test("text links and the Show passwords row are at least 24px tall (QA-006, WCAG 2.5.8)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  for (const locator of [page.getByRole("link", { name: "← Back to dashboard" }), page.getByText("Show passwords")]) {
    expect((await locator.boundingBox())!.height).toBeGreaterThanOrEqual(24);
  }
  await fillAndSubmit(page, "not-the-password", NEW_PASSWORD);
  const forgot = page.getByRole("link", { name: "Forgot your current password?" });
  await expect(forgot).toBeVisible();
  expect((await forgot.boundingBox())!.height).toBeGreaterThanOrEqual(24);
});

test("while the request is pending the button keeps keyboard focus and progress is announced (QA-009)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  await page.route("**/api/v1/auth/change-password", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.getByLabel("Current password").fill("not-the-password");
  await page.getByLabel("New password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Change password" }).click();
  const busy = page.getByRole("button", { name: "Changing…" });
  await expect(busy).toBeVisible();
  await expect(busy).toBeFocused();
  await expect(busy).toHaveCSS("opacity", "0.6"); // still dimmed like a disabled .btn
  await expect(page.locator("[role=status]").filter({ hasText: "Changing your password…" })).toHaveCount(1);
  await expect(page.locator(".form-error")).toContainText("Incorrect current password"); // and it settles normally
});

test("an employer, whose dashboard has no portal shell, reaches the page from a link on it (QA-003)", async ({ page }) => {
  const email = `enh006-emp-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}@example.local`;
  const registered = await page.request.post("/api/v1/employer/register", {
    data: { email, password: OLD_PASSWORD, full_name: "E2E Employer", company_name: `E2E Company ${Date.now()}-${Math.floor(Math.random() * 1_000_000)}` }, // company names are unique
  });
  expect(registered.ok()).toBeTruthy();
  await page.goto("/it/employer/dashboard");
  await page.getByRole("link", { name: "Change password" }).click();
  await page.waitForURL("**/account/password");
  await expect(page.getByRole("link", { name: "← Back to dashboard" })).toHaveAttribute("href", "/it/employer/dashboard");
});

test("a keyboard user can skip the site header: one Tab reaches the skip link, Enter lands in the content (QA-008)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  const box = (await skip.boundingBox())!;
  expect(box.x, "the skip link is on screen when focused").toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "← Back to dashboard" })).toBeFocused();
});

test("a whitespace-only new password is refused with a clear message and the field is focused (QA-007)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  await fillAndSubmit(page, OLD_PASSWORD, " ".repeat(12));
  await expect(page.locator(".form-error")).toContainText("Password must not consist only of spaces");
  await expect(page.getByLabel("New password")).toBeFocused();
});
