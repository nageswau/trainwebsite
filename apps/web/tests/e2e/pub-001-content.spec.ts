import { test, expect } from "@playwright/test";

// PUB-001 -- Corporate & IT marketing content: Career Paths, Real Projects, Success
// Stories, Business Services. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied.

test("career paths list shows seeded items and links to a working detail page (PUB-001-AC01)", async ({ page }) => {
  await page.goto("/it/career-paths");
  const firstCard = page.locator(".card").filter({ has: page.getByRole("link", { name: "View roadmap" }) }).first();
  await expect(firstCard).toBeVisible();
  await firstCard.getByRole("link", { name: "View roadmap" }).click();
  await expect(page.getByText("Skills you'll build")).toBeVisible();
  await expect(page.getByText("Career outcomes")).toBeVisible();
});

test("career path detail 404s gracefully for an unknown slug, not a broken page (PUB-001-AC02)", async ({ page }) => {
  await page.goto("/it/career-paths/no-such-path");
  await expect(page.getByRole("heading", { name: "Career path not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to career paths" })).toBeVisible();
});

test("real projects list shows seeded items with tech stack and a working detail page", async ({ page }) => {
  await page.goto("/it/real-projects");
  const firstCard = page.locator(".card").filter({ has: page.getByRole("link", { name: "View project" }) }).first();
  await expect(firstCard).toBeVisible();
  await firstCard.getByRole("link", { name: "View project" }).click();
  await expect(page.getByText("What you'll build")).toBeVisible();
  await expect(page.getByText("Tech stack")).toBeVisible();
});

test("success stories list shows seeded testimonials with a working detail page", async ({ page }) => {
  await page.goto("/it/success-stories");
  const firstCard = page.locator(".card").filter({ has: page.getByRole("link", { name: "Read story" }) }).first();
  await expect(firstCard).toBeVisible();
  await firstCard.getByRole("link", { name: "Read story" }).click();
  await expect(page.getByText(/—/)).toBeVisible();
});

test("business services page shows published content and a contact CTA", async ({ page }) => {
  await page.goto("/it/business-services");
  await expect(page.getByRole("heading", { name: "Business Services" })).toBeVisible();
  await expect(page.getByText("Corporate training")).toBeVisible();
  await expect(page.getByRole("link", { name: "Talk to our business team" })).toHaveAttribute("href", "/it/contact");
});

test("all four new sections are reachable from the public IT navigation", async ({ page }) => {
  // These four now live under the "Programs" dropdown (grouped to de-clutter the header
  // nav, which had grown to 12 flat items) rather than as top-level links -- still
  // reachable from the nav, just one click away instead of zero.
  await page.goto("/it");
  await page.getByRole("button", { name: "Programs" }).click();
  for (const label of ["Career Paths", "Real Projects", "Success Stories", "Business Services"]) {
    await expect(page.getByRole("navigation").getByRole("link", { name: label })).toBeVisible();
  }
});

test("public content pages require no authentication and are usable at a 375px viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/it/career-paths");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "View roadmap" }).first()).toBeVisible();
});
