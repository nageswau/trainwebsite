import { test, expect } from "@playwright/test";

// PUB-005 -- News and gallery (CMS-managed). News (BlogPost) already had full admin CRUD
// and a working public page; the real gap was GalleryItem having no admin publish path
// at all. Confirms a Super Admin can publish a gallery item through the real new UI
// action and it shows up in the admin's own management list. Deliberately does not also
// assert the item appears on the public /gallery page in the same run -- publicApi()
// caches with `next: { revalidate: 60 }`, so a freshly published item is not guaranteed
// to be visible there within a single test run (same known Next.js fetch-cache
// transient-staleness pattern documented in pending.md for other public-content pages);
// the public read path itself is pre-existing, unchanged code, not this feature's gap.

test("Super Admin publishes a gallery item through the real UI action (PUB-005-AC01)", async ({ page }) => {
  const uniqueTitle = `E2E Gallery Item ${Date.now()}`;

  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");

  await page.goto("/admin/gallery");
  await expect(page.getByRole("heading", { name: "Publish gallery item" })).toBeVisible();
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Publish gallery item" }) });
  await card.locator("select[name='division']").selectOption("it");
  await card.locator("input[name='title']").fill(uniqueTitle);
  await card.locator("input[name='image_url']").fill("https://example.local/e2e-gallery-item.jpg");
  await card.getByRole("button", { name: "Publish gallery item" }).click();
  await expect(card.getByText("Gallery item saved.")).toBeVisible();

  const searchBox = page.getByLabel("Search records");
  await searchBox.fill(uniqueTitle);
  const row = page.locator("table tbody tr", { hasText: uniqueTitle });
  await expect(row).toBeVisible();
  await expect(row).toContainText("true");
});

test("a non-admin cannot publish a gallery item at the API layer (PUB-005-AC03)", async ({ page }) => {
  await page.request.post("/api/v1/auth/login", { data: { email: "student.it@edusphere.local", password: "Demo@123", division: "it" } });
  const response = await page.request.post("/api/v1/cms/gallery", { data: { division: "it", title: "Unauthorized", image_url: "https://example.local/x.jpg" } });
  expect(response.status()).toBe(403);
});

test("the gallery management console requires authentication", async ({ page }) => {
  await page.goto("/admin/gallery");
  await expect(page).toHaveURL(/\/admin\/login/);
});
