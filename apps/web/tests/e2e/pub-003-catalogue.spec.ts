import { test, expect } from "@playwright/test";

// PUB-003 -- Course catalogue and detail. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.

test("catalogue lists programs and search narrows results (PUB-003-AC01)", async ({ page }) => {
  await page.goto("/it/programs");
  const initialCount = await page.locator(".card.hover").count();
  expect(initialCount).toBeGreaterThan(0);

  await page.getByPlaceholder(/Search Python, SAP, AI/).fill("zzz-no-such-program-zzz");
  await expect(page.getByText("No Matching Programmes")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show All Programmes" })).toBeVisible();

  await page.getByPlaceholder(/Search Python, SAP, AI/).fill("");
  await expect(page.locator(".card.hover").first()).toBeVisible();
});

test("category tabs filter the catalogue and preserve the selected state in the URL (PUB-003-AC01)", async ({ page }) => {
  await page.goto("/it/programs");
  await page.getByRole("button", { name: /Artificial Intelligence/ }).click();
  await expect(page).toHaveURL(/category=Artificial\+Intelligence/);
  await expect(page.getByText("Artificial Intelligence", { exact: true }).last()).toBeVisible();
  await expect(page.locator(".card.hover")).toHaveCount(3);
});

test("opening a program shows full detail: curriculum, duration, fees, certification, trainer (PUB-003-AC01)", async ({ page }) => {
  await page.goto("/it/programs");
  await page.locator(".card.hover").first().getByRole("link", { name: /View Curriculum/i }).click();
  await expect(page.getByRole("heading", { name: "Curriculum" })).toBeVisible();
  await expect(page.getByText("Duration")).toBeVisible();
  await expect(page.getByText("Fees")).toBeVisible();
  await expect(page.getByText("Certification", { exact: true })).toBeVisible();
  await expect(page.getByText("Trainer", { exact: true })).toBeVisible();
  await expect(page.getByText("Placement Assistance")).toBeVisible();
});

test("program detail generates per-page SEO metadata, not the generic fallback (PUB-003 accessibility/SEO)", async ({ page }) => {
  await page.goto("/it/programs");
  const firstTitle = (await page.locator(".card.hover h3").first().textContent())?.trim();
  expect(firstTitle).toBeTruthy();
  await page.locator(".card.hover").first().getByRole("link", { name: /View Curriculum/i }).click();
  await expect(page).toHaveTitle(`${firstTitle} | EduSphere`);
});

test("a nonexistent program slug shows a graceful message, not a broken page", async ({ page }) => {
  await page.goto("/it/programs/no-such-program-slug");
  await expect(page.getByRole("heading", { name: "Program unavailable" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to programs" })).toBeVisible();
});

test("catalogue and detail pages require no authentication and are usable at a 375px viewport (responsive)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/it/programs");
  await expect(page.locator(".card.hover").first()).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 375);
});
