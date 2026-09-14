import { test, expect } from "@playwright/test";

// PUB-004 -- Webinar listing and registration. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds one IT-division
// upcoming webinar, "GenAI Career Webinar").

test("webinars list shows the seeded upcoming webinar and links to a detail page (PUB-004-AC01)", async ({ page }) => {
  await page.goto("/it/webinars");
  await expect(page.getByRole("heading", { name: "Upcoming", exact: true })).toBeVisible();
  const card = page.locator(".card").filter({ has: page.getByRole("heading", { name: "GenAI Career Webinar" }) });
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: /View & register/ }).click();
  await expect(page.getByRole("heading", { name: "GenAI Career Webinar" })).toBeVisible();
});

test("webinar detail 404s gracefully for an unknown id, not a broken page", async ({ page }) => {
  await page.goto("/it/webinars/00000000-0000-0000-0000-000000000000");
  await expect(page.getByRole("heading", { name: "Webinar not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to webinars" })).toBeVisible();
});

test("visitor can register for an upcoming webinar with no authentication (PUB-004-AC01/AC03)", async ({ page }) => {
  await page.goto("/it/webinars");
  await page.locator(".card").filter({ has: page.getByRole("heading", { name: "GenAI Career Webinar" }) }).getByRole("link", { name: /View & register/ }).click();

  const unique = Date.now();
  await page.getByLabel("Full name *").fill(`PUB-004 Visitor ${unique}`);
  await page.getByLabel("Email *").fill(`pub004-${unique}@example.com`);
  await page.getByRole("button", { name: "Register for this webinar" }).click();
  await expect(page.getByText(/Registration confirmed/)).toBeVisible();
});

test("webinars are reachable from the public IT navigation", async ({ page }) => {
  await page.goto("/it");
  await page.getByRole("button", { name: "Programs" }).click();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Webinars" })).toBeVisible();
});

test("webinars page requires no authentication and is usable at a 375px viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/it/webinars");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
