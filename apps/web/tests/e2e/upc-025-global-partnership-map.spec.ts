import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-025 (AC1-AC3, AC9): a partnership head opens the Global Partnership Map from the menu, filters it to a region, reads Iceland's four
// counts from its focused link and the hover panel, tabs to a small country's marker, switches to the table (same figures), and selects
// Iceland -- the Global University Database lists exactly that many universities (the same filters + iso2). The page fits a phone. The
// shared database holds other rows, so counts are compared between the map and the search rather than fixed.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const country = async (q: string) => (await (await page.request.get(`/api/v1/lookups/countries?q=${encodeURIComponent(q)}&limit=5`)).json()).items[0].id;
  const [iceland, singapore] = [await country("Iceland"), await country("Singapore")];
  const university = async (label: string, countryId: string, stage: string | null) => {
    const { university: u } = await post("/api/v1/partnership/universities", { name: `E2E Map ${label} ${stamp}`, country_id: countryId, city: "City" });
    if (stage) await post(`/api/v1/partnership/universities/${u.id}/stage`, { from_stage: "target_university", to_stage: stage });
  };
  await university("Partner", iceland, "active_partner");
  await university("Talking", iceland, "meeting_completed");
  await university("Prospect", iceland, null);
  await university("Lion", singapore, "interested");
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc025-h-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, head.development_welcome_token);
  return head;
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const counts = (label: string) => label.match(/(\d+) partner, (\d+) in progress, (\d+) target, (\d+) lost/)!.slice(1).map(Number);

test("a head reads the Global Partnership Map by keyboard, as a table, and opens a country's universities", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const head = await setUp(page, stamp);

  // AC9: the §32 menu entry opens the page.
  await signIn(page, "/admin/login", head.email);
  await page.getByRole("link", { name: "Global Partnership Map" }).first().click();
  await expect(page.getByRole("heading", { name: "Global Partnership Map" })).toBeVisible();
  const form = page.getByRole("form", { name: "Map filters" });
  await form.getByLabel("Region").selectOption("Europe");
  await form.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/region=Europe/);

  // AC2: Iceland is a named, focusable link; focus shows its counts in the panel. Asia's Singapore is filtered out.
  const map = page.getByRole("group", { name: "World map of university partnerships" });
  const iceland = map.locator("a[aria-label^='Iceland:']");
  const label = (await iceland.getAttribute("aria-label")) as string;
  const [partner, inProgress, target, lost] = counts(label);
  expect(partner).toBeGreaterThanOrEqual(1);
  expect(inProgress).toBeGreaterThanOrEqual(1);
  expect(target).toBeGreaterThanOrEqual(1);
  await iceland.focus();
  await expect(page.locator(".map-panel")).toHaveText(`Iceland ${partner} partner ${inProgress} in progress ${target} target ${lost} lost / closed`);
  await expect(iceland).toHaveClass(/map-partner/); // MP11: at least one partner
  await expect(map.locator("a[aria-label^='Singapore:']")).toHaveCount(0);

  // AC3: the table shows the same figures.
  await page.getByRole("navigation", { name: "Map view" }).getByRole("link", { name: "Table" }).click();
  await expect(page).toHaveURL(/region=Europe.*view=table/);
  const row = page.getByRole("region", { name: "Universities by country" }).getByRole("row").filter({ hasText: "Iceland" });
  await expect(row.getByRole("cell")).toHaveText(["Iceland", "Europe", String(partner), String(inProgress), String(target), String(lost), String(partner + inProgress + target + lost)]);

  // AC1: Iceland opens the Global University Database with the same filters and its exact code; the totals agree.
  await row.getByRole("link", { name: "Iceland" }).click();
  await expect(page).toHaveURL(/\/partnership\/search\?region=Europe&iso2=IS/);
  await expect(page.getByRole("navigation", { name: "Partner status" }).getByRole("link")).toHaveText([
    `Any (${partner + inProgress + target + lost})`, `Partner (${partner})`, `Partnership in progress (${inProgress})`, `Target (${target})`,
    `Not partnered (${inProgress + target})`, `Lost / closed (${lost})`,
  ]);
  await expect(page.getByRole("link", { name: "Remove Country: Iceland" })).toBeVisible();

  // MP13: back on the whole map, Singapore is reached by Tab as a marker.
  await page.goto("/partnership/map");
  const singapore = page.locator("svg a[aria-label^='Singapore:']");
  await expect(singapore.locator("circle")).toHaveCount(1);
  await singapore.focus();
  await expect(page.locator(".map-panel")).toContainText("Singapore");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/partnership\/search\?iso2=SG/);

  // AC9: the page fits a phone.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/partnership/map");
  await expect(page.getByRole("heading", { name: "Global Partnership Map" })).toBeVisible();
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
});
