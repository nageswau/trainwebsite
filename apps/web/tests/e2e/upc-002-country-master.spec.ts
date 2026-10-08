import { test, expect } from "@playwright/test";

// upc-002 -- country master. Migration 0100 seeds every ISO country as an internal row; the public catalogue still shows only the
// seeded catalogue countries, and the admin university form still offers only those. Requires the stack running via
// `docker compose up` with `python -m app.seed` applied.

const CATALOGUE = ["Australia", "Canada", "Dubai (UAE)", "France", "Germany", "Ireland", "Netherlands", "New Zealand", "Singapore", "Sweden", "USA", "United Kingdom"];
const INTERNAL = ["Japan", "India", "United States", "United Arab Emirates", "Antarctica"];

test("the public destination list still shows the catalogue countries and no internal ISO country (upc-002-AC1)", async ({ page }) => {
  await page.goto("/overseas/countries");
  await expect(page.getByRole("heading", { name: "Study Destinations" })).toBeVisible();
  await page.getByLabel("Per page").selectOption("18"); // the list pages client-side (9 by default); one page holds the catalogue
  await expect(page.getByText("Page 1 of 1")).toBeVisible();
  for (const name of CATALOGUE) await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  for (const name of INTERNAL) await expect(page.getByRole("heading", { name, exact: true })).toHaveCount(0);
});

test("a catalogue country keeps its guide; an internal one is the unavailable page (upc-002-AC1)", async ({ page }) => {
  await page.goto("/overseas/countries/dubai-uae");
  await expect(page.getByRole("heading", { name: "Dubai (UAE)", exact: true })).toBeVisible();
  await page.goto("/overseas/countries/japan");
  await expect(page.getByRole("heading", { name: "Country guide unavailable" })).toBeVisible();
});

test("an overseas admin creates universities only in catalogue countries, and can look up every country", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/universities");
  const select = page.locator("#university-country");
  await expect(select).toBeEnabled();
  const options = await select.locator("option").allTextContents();
  for (const name of CATALOGUE) expect(options).toContain(name);
  for (const name of INTERNAL) expect(options).not.toContain(name);

  const lookup = await page.request.get("/api/v1/lookups/countries", { params: { q: "jp" } });
  expect(lookup.status()).toBe(200);
  expect((await lookup.json()).items[0]).toMatchObject({ label: "Japan", detail: "JP · Asia" });
});

test("the country lookup is closed to the public and to other roles", async ({ page }) => {
  expect((await page.request.get("/api/v1/lookups/countries")).status()).toBe(401);
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect((await page.request.get("/api/v1/lookups/countries")).status()).toBe(403);
});
