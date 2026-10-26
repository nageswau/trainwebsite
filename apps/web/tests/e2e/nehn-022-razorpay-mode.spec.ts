import { test, expect, type Page } from "@playwright/test";

// nehn-022 (DEC-SCOPE-283): the stack runs with RAZORPAY_MODE=test (the default), so the student Fee Payments card shows the test-mode
// banner and Admin -> Settings shows the mode. Live hides the banner (vitest: PaymentModeBanner / FeePaymentPanel) -- flipping a stack
// to live needs real rzp_live_ keys, and the API refuses to start without them (pytest: test_nehn_022_razorpay_mode.py).
const BANNER = "Test mode: payments here use Razorpay test mode and no real money is charged.";

async function signIn(page: Page, path: string, email: string) {
  await page.goto(path);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("nehn-022 AC2: a student sees the test-mode banner on Fee Payments", async ({ page }) => {
  await signIn(page, "/it/login", "student.it@edusphere.local");
  await page.goto("/it/student/fees");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Fee Payments" }) });
  await expect(card.getByText(BANNER)).toBeVisible();
});

test("nehn-022: Admin Settings shows the Razorpay mode, never a key", async ({ page }) => {
  await signIn(page, "/admin/login", "superadmin@edusphere.local");
  await page.goto("/admin/settings");
  const row = page.getByRole("row", { name: /Razorpay mode/ });
  await expect(row).toContainText("test mode");
  await expect(page.locator("main")).not.toContainText("rzp_");
});

test("nehn-022: the mode read needs a session", async ({ request }) => {
  expect((await request.get("/api/v1/payments/mode")).status()).toBe(401);
});
