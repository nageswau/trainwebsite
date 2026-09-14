import { test, expect } from "@playwright/test";

// OVS-007 -- Events and workshops (Overseas division). Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds two upcoming
// overseas events with no external registration_url: "UK University Application
// Workshop", "Study Abroad Education Fair").

test("events list shows seeded overseas events and links to a detail page (OVS-007-AC01)", async ({ page }) => {
  await page.goto("/overseas/events");
  // The listing paginates client-side (RAID.md I-07's DataTable pattern, also true of
  // CollectionExplorer) -- the shared dev DB has accumulated enough test-created events
  // that a seeded row can sit past page 1. Search to it first rather than asserting on
  // the raw unpaginated list.
  await page.getByLabel("Search events").fill("UK University Application Workshop");
  const card = page.locator(".card").filter({ has: page.getByRole("heading", { name: "UK University Application Workshop" }) });
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: /View & register/ }).click();
  await expect(page.getByRole("heading", { name: "UK University Application Workshop" })).toBeVisible();
});

test("event detail 404s gracefully for an unknown id", async ({ page }) => {
  await page.goto("/overseas/events/00000000-0000-0000-0000-000000000000");
  await expect(page.getByRole("heading", { name: "Event not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to events" })).toBeVisible();
});

test("visitor can register for an overseas event with no authentication (OVS-007-AC01)", async ({ page }) => {
  await page.goto("/overseas/events");
  await page.getByLabel("Search events").fill("Study Abroad Education Fair");
  await page.locator(".card").filter({ has: page.getByRole("heading", { name: "Study Abroad Education Fair" }) }).getByRole("link", { name: /View & register/ }).click();

  const unique = Date.now();
  await page.getByLabel("Full name *").fill(`OVS-007 Visitor ${unique}`);
  await page.getByLabel("Email *").fill(`ovs007-${unique}@example.com`);
  await page.getByRole("button", { name: "Register for this event" }).click();
  await expect(page.getByText(/Registration confirmed/)).toBeVisible();
});

test("events page requires no authentication and is usable at a 375px viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/overseas/events");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
