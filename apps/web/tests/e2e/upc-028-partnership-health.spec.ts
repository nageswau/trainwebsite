import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-028 (AC4, AC6, AC9): a manager moves a new university to Active Partner -- its health card reads "Insufficient data"; once a
// student applies, the score is 1/100 – Needs attention (one application of the 20 that count as full, every other counted factor 0)
// with a breakdown whose points add up to it, on the university page and in the University Performance Health column. An overseas_admin
// sees the band but no breakdown. The page fits a phone. Throwaway accounts via the real admin API.

async function apiLogin(request: APIRequestContext, email: string, password: string, division: string) {
  await request.post("/api/v1/auth/logout");
  const response = await request.post("/api/v1/auth/login", { data: { email, password, division } });
  expect(response.ok(), await response.text()).toBe(true);
}

async function call(request: APIRequestContext, url: string, data: unknown) {
  const response = await request.post(url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  const r = page.request;
  await apiLogin(r, "superadmin@edusphere.local", "Demo@123", "global");
  const head = await call(r, "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc028-h-${stamp}@example.local` });
  const manager = await call(r, "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc028-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U28-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await call(r, "/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc028-a-${stamp}@example.local` });
  const countries = await (await r.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await call(r, "/api/v1/partnership/universities", { name: `E2E Health University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await call(r, `/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await r.post("/api/v1/auth/logout");
  for (const user of [manager, admin]) await activateWithToken(r, user.development_welcome_token);
  await apiLogin(r, manager.email, E2E_PASSWORD, "overseas");
  await call(r, `/api/v1/partnership/universities/${university.id}/stage`, { from_stage: university.pipeline.stage, to_stage: "active_partner" });
  await r.post("/api/v1/auth/logout");
  return { manager, admin, university };
}

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test("a partner's health score: insufficient data, then a scored breakdown; overseas_admin sees the band only", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { manager, admin, university } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;
  const card = page.getByRole("region", { name: "Partnership health" });

  // AC4: a new partner with no data.
  await signIn(page, manager.email);
  await page.goto(universityPage);
  await expect(card.locator(".health-unknown")).toHaveText("Insufficient data");
  await expect(card).toContainText("Not enough activity yet");

  // A student applies: the score appears with its breakdown (commission role), and the points add up to it (AC1).
  await apiLogin(page.request, "student.overseas@edusphere.local", "Demo@123", "overseas");
  await call(page.request, "/api/v1/workflows/overseas/applications", { university_id: university.id, intake: "Sep 2027" });
  await signIn(page, manager.email);
  await page.goto(universityPage);
  await expect(card.getByText("1/100 – Needs attention")).toBeVisible();
  const breakdown = card.getByRole("table", { name: /Health score breakdown/ });
  await expect(breakdown.getByRole("row", { name: /Student applications/ })).toContainText("1 in the last 12 months");
  await expect(breakdown.getByRole("row", { name: /Offers/ })).toContainText("0 of 1 applications (0%)");
  await expect(breakdown.getByRole("row", { name: /Visa success/ })).toContainText("No data"); // no decisions: its weight is shared out
  await expect(breakdown.getByRole("row", { name: /Student satisfaction/ })).toContainText("Not tracked");
  await expect(breakdown.getByRole("row", { name: /Commission/ })).toContainText("No expected commission");
  await expect(breakdown.getByRole("row", { name: "Score" })).toContainText("1");

  // The ranking's Health column, keyboard-reachable table region.
  await page.goto("/partnership/performance");
  const row = page.getByRole("rowheader", { name: university.name }).locator("xpath=..");
  await expect(row).toContainText("1/100 – Needs attention");
  await expect(page.getByRole("columnheader", { name: "Health" })).toBeVisible();
  await expect(page.getByText(/Health is scored as of today/)).toBeVisible();

  // AC9: phone width -- no page side-scroll on either page.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(universityPage);
  await expect(card.getByText("1/100 – Needs attention")).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
  await page.goto("/partnership/performance");
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC6: overseas_admin -- the band, never the breakdown.
  await signIn(page, admin.email);
  await page.goto(universityPage);
  await expect(card.getByText("1/100 – Needs attention")).toBeVisible();
  await expect(card.getByRole("table")).toHaveCount(0);
  const api = await (await page.request.get(`/api/v1/partnership/universities/${university.id}/performance`)).json();
  expect(Object.keys(api.health).sort()).toEqual(["as_of", "band", "band_label", "score"]);
});
