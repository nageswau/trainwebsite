import { test, expect } from "@playwright/test";

// OVS-001 -- Destination/university/course discovery. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds Germany as a
// country and University of Manchester as a university, among others).

test("country list shows a seeded destination and links to its detail page (OVS-001-AC01)", async ({ page }) => {
  await page.goto("/overseas/countries");
  await expect(page.getByRole("heading", { name: "Study Destinations" })).toBeVisible();
  const card = page.locator(".card").filter({ has: page.getByRole("heading", { name: "Germany" }) });
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: "Country guide" }).click();
  await expect(page.getByRole("heading", { name: "Germany", exact: true })).toBeVisible();
});

test("country detail 404s gracefully for an unknown slug, not a broken page", async ({ page }) => {
  await page.goto("/overseas/countries/no-such-country");
  await expect(page.getByRole("heading", { name: "Country guide unavailable" })).toBeVisible();
});

test("university list is searchable and links to a detail page with its courses (OVS-001-AC01)", async ({ page }) => {
  await page.goto("/overseas/universities");
  await expect(page.getByRole("heading", { name: "Partner & Featured Universities" })).toBeVisible();
  // Search down to this run's target first -- the generic list paginates client-side
  // and can otherwise legitimately sit on page 2+ behind accumulated dev-DB debris
  // (RAID.md I-07), which is not a defect in this feature.
  await page.getByPlaceholder(/Search university/).fill("University of Manchester");
  await expect(page.getByRole("heading", { name: "University of Manchester" })).toBeVisible();
  await page.getByRole("link", { name: "University profile" }).click();
  await expect(page.getByRole("heading", { name: "University of Manchester" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Courses" })).toBeVisible();
});

test("university detail 404s gracefully for an unknown slug, not a broken page", async ({ page }) => {
  await page.goto("/overseas/universities/no-such-university");
  await expect(page.getByRole("heading", { name: "University unavailable" })).toBeVisible();
});

test("course list renders seeded overseas courses (OVS-001-AC01)", async ({ page }) => {
  await page.goto("/overseas/courses");
  await expect(page.getByRole("heading", { name: "Overseas Courses" })).toBeVisible();
  await expect(page.locator(".card").first()).toBeVisible();
});

test("discovery pages are reachable from the overseas public navigation with no authentication", async ({ page }) => {
  await page.goto("/overseas");
  const nav = page.getByRole("navigation");
  await nav.getByRole("link", { name: "Countries" }).click();
  await expect(page).toHaveURL(/\/overseas\/countries$/);
  await page.goto("/overseas");
  await nav.getByRole("link", { name: "Universities" }).click();
  await expect(page).toHaveURL(/\/overseas\/universities$/);
  await page.goto("/overseas");
  await nav.getByRole("link", { name: "Courses" }).click();
  await expect(page).toHaveURL(/\/overseas\/courses$/);
});

test("discovery pages are usable at a 375px viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/overseas/countries");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
