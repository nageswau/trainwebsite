import { test, expect, type Page } from "@playwright/test";

// ENH-014 -- notification preferences on /account/profile. Uses the seeded School Parent and restores its phone and
// preferences at the end (shared seeded state, AGENTS.md "Test caveats").
const PREFS = "/api/v1/account/notification-preferences";

async function signIn(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "school.parent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/parent/**");
  await page.goto("/account/profile");
}

async function restore(page: Page, phone: string) {
  await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
  await page.request.patch("/api/v1/auth/me", { data: { phone: phone || null } });
}

test("a parent adds a phone, turns on WhatsApp, and it persists", async ({ page }) => {
  await signIn(page);
  const originalPhone = await page.locator("#profile-phone").inputValue();
  try {
    await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
    await page.request.patch("/api/v1/auth/me", { data: { phone: null } });
    await page.reload();

    const whatsapp = page.getByRole("checkbox", { name: /^WhatsApp/ });
    await expect(whatsapp).toBeDisabled();
    await expect(page.getByText("in your profile above to turn on WhatsApp or SMS.")).toBeVisible();

    await page.fill("#profile-phone", "+91 98765 43210");
    await page.click("button:has-text('Save changes')");
    await expect(page.getByText("Your profile was updated.")).toBeVisible();
    await expect(whatsapp).toBeEnabled(); // router.refresh(), no manual reload

    await whatsapp.check();
    await page.getByRole("button", { name: "Save notification settings" }).click();
    await expect(page.getByText("Notification settings saved.")).toBeVisible();
    await page.reload();
    await expect(page.getByRole("checkbox", { name: /^WhatsApp/ })).toBeChecked();
    await expect(page.getByRole("checkbox", { name: /^Email/ })).toBeDisabled();
  } finally {
    await restore(page, originalPhone);
  }
});

test("keyboard only: tab to SMS, toggle with Space, save with Enter", async ({ page }) => {
  await signIn(page);
  const originalPhone = await page.locator("#profile-phone").inputValue();
  try {
    await page.request.patch("/api/v1/auth/me", { data: { phone: "+91 98765 43210" } });
    await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
    await page.reload();
    const sms = page.getByRole("checkbox", { name: /^SMS/ });
    await sms.focus();
    await page.keyboard.press("Space");
    await expect(sms).toBeChecked();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Save notification settings" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Notification settings saved.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save notification settings" })).toBeFocused();
  } finally {
    await restore(page, originalPhone);
  }
});

for (const width of [320, 1440]) {
  test(`Notifications section fits ${width}px with labelled controls`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page);
    // The shared site header already overflows the document at 320px on this page (pre-existing, not ENH-014), so assert
    // on the Notifications section itself: nothing inside it may extend past the viewport.
    const sectionOverflow = await page.evaluate(() => {
      const w = document.documentElement.clientWidth;
      const group = document.querySelector("fieldset");
      const section = group?.closest("section") ?? group?.parentElement;
      if (!section) return Number.POSITIVE_INFINITY;
      return Math.max(0, ...Array.from(section.querySelectorAll("*")).map((e) => e.getBoundingClientRect().right - w));
    });
    expect(sectionOverflow).toBeLessThanOrEqual(0);
    await expect(page.getByRole("heading", { level: 2, name: "Notifications" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Send me updates by" })).toBeVisible();
    for (const name of [/^Email/, /^In-app/, /^WhatsApp/, /^SMS/]) {
      const box = page.getByRole("checkbox", { name });
      await expect(box).toBeVisible();
      const row = await box.locator("xpath=ancestor::label").boundingBox();
      expect(row!.height).toBeGreaterThanOrEqual(44);
    }
  });
}

test("a failed save shows a retryable alert, reverts the box, and leaves the profile form usable", async ({ page }) => {
  await signIn(page);
  const originalPhone = await page.locator("#profile-phone").inputValue();
  try {
    await page.request.patch("/api/v1/auth/me", { data: { phone: "+91 98765 43210" } });
    await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
    await page.reload();
    // Only the browser's PUT is intercepted; the server-rendered GET (and page.request) are not.
    await page.route(`**${PREFS}`, (route) => (route.request().method() === "PUT" ? route.fulfill({ status: 500, body: "{}" }) : route.continue()));
    const sms = page.getByRole("checkbox", { name: /^SMS/ });
    await sms.check();
    await page.getByRole("button", { name: "Save notification settings" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Couldn't save" })).toContainText("Couldn't save your settings. Check your connection and try again.");
    await expect(sms).not.toBeChecked();
    await expect(page.locator("#profile-full-name")).toBeEditable();
  } finally {
    await page.unroute(`**${PREFS}`);
    await restore(page, originalPhone);
  }
});
