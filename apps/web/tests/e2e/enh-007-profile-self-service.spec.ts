import { test, expect } from "@playwright/test";

// ENH-007 -- Profile Self-Service. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied (seeds school.coordinator@edusphere.local / Demo@123,
// apps/api/app/seed.py:622). All 7 School-domain roles share the identical
// shell/route/component with no role-conditional logic (spec §8), so this one seeded role is
// sufficient evidence -- not one spec per role.

test("a School-domain user can find, view, and edit their profile from the portal", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "school.coordinator@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.click("a:has-text('My profile')");
  await page.waitForURL("**/account/profile");
  await expect(page.locator("h1")).toHaveText("Your profile");

  // Capture the original seeded values so this shared demo account can be restored afterwards
  // (same pattern the second test in this file already uses with its own `before` capture) --
  // this account is reused by every run of this spec, not a throwaway created per-test.
  const originalName = await page.locator("#profile-full-name").inputValue();
  const originalPhone = await page.locator("#profile-phone").inputValue();

  const unique = Date.now();
  const newName = `E2E Updated Name ${unique}`;
  await page.fill("#profile-full-name", newName);
  await page.fill("#profile-phone", "+91 90000 00000");
  await page.click("button:has-text('Save changes')");
  await expect(page.getByText("Your profile was updated.")).toBeVisible();

  await page.reload();
  await expect(page.locator("#profile-full-name")).toHaveValue(newName);
  await expect(page.locator("#profile-phone")).toHaveValue("+91 90000 00000");

  // Restore the shared seeded account's original values so this test doesn't leave it corrupted
  // for the next run or for any other spec that logs in as school.coordinator@edusphere.local.
  await page.fill("#profile-full-name", originalName);
  await page.fill("#profile-phone", originalPhone);
  await page.click("button:has-text('Save changes')");
  await expect(page.getByText("Your profile was updated.")).toBeVisible();
});

test("a full name under 2 characters is rejected with a field-level error and nothing is saved", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "school.coordinator@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/account/profile");
  const before = await page.locator("#profile-full-name").inputValue();
  await page.fill("#profile-full-name", "A");
  await page.click("button:has-text('Save changes')");
  await expect(page.locator("#profile-full-name")).toHaveAttribute("aria-invalid", "true");

  await page.reload();
  await expect(page.locator("#profile-full-name")).toHaveValue(before);
});

test("a signed-out visit to /account/profile prompts sign-in and returns after login", async ({ page }) => {
  await page.goto("/account/profile");
  await expect(page.locator("h1")).toHaveText("Sign in required");
  await page.click("a:has-text('Overseas Education sign in')");
  await page.fill("#login-email", "school.coordinator@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/account/profile");
  await expect(page.locator("h1")).toHaveText("Your profile");
});
