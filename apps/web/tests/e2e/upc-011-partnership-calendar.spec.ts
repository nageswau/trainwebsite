import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-011 (AC1, AC2, P1, N1, E1): a partnership manager plans two visits, then adds an education fair spanning that week from the
// calendar; the event page warns that it overlaps both visits (AC2 on create) and the calendar flags them. The week and month views
// show the fair on each of its days; cancelling it takes it off the calendar. The head reads the team calendar and picks the manager.
// Throwaway accounts via the real admin API.

const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, path: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(path);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc011-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc011-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U11-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Calendar University ${stamp}`, country_id: countries.items[0].id, city: "Leeds" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, university };
}

test("an education fair week with two visits warns of the overlaps; head reads the team calendar", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, manager, university } = await setUp(page, stamp);
  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");

  // Two visits (upc-010), planned through the API.
  const visits: string[] = [];
  for (const offset of [8, 10]) {
    const response = await page.request.post("/api/v1/partnership/visits", { data: { university_id: university.id, purpose: "Campus tour", proposed_date: inDays(offset) } });
    expect(response.ok(), await response.text()).toBe(true);
    visits.push((await response.json()).visit.code);
  }

  await page.getByRole("link", { name: "Calendar", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Your calendar" })).toBeVisible();
  await page.getByRole("link", { name: "Add an event" }).click();
  await expect(page.getByRole("heading", { name: "Add a partnership event" })).toBeVisible();
  await page.getByRole("button", { name: "Add event" }).click();
  await expect(page.getByText("Choose the event type")).toBeVisible();

  await page.getByLabel("Event type").selectOption("education_fair");
  await page.getByLabel("Title").fill(`QS Fair ${stamp}`);
  await page.getByLabel("Start date").fill(inDays(7));
  await page.getByLabel("End date").fill(inDays(11));
  await page.getByLabel("Location").fill("Delhi, Pragati Maidan");
  await page.getByRole("button", { name: "Add event" }).click();
  await page.waitForURL(/\/partnership\/events\/[0-9a-f-]{36}$/);
  const detail = page.url();

  // AC2 on create: the event page names both visits.
  await expect(page.getByRole("heading", { name: `QS Fair ${stamp}` })).toBeVisible();
  const notice = page.getByRole("note").filter({ hasText: "Overlaps with other plans" });
  for (const code of visits) await expect(notice.getByRole("link", { name: new RegExp(code) })).toBeVisible();

  // AC1 / E1: the week shows the fair on each of its days and flags the visits.
  await page.goto(`/partnership/calendar?view=week&date=${inDays(8)}`);
  await expect(page.getByRole("note").filter({ hasText: /items? overlap/ })).toBeVisible();
  const visitDay = page.getByRole("region").filter({ has: page.getByRole("link", { name: new RegExp(`^${visits[0]} — `) }) });
  await expect(visitDay.getByText("University visit")).toBeVisible();
  await expect(visitDay.getByText("Education fair")).toBeVisible();
  await expect(visitDay.getByText(/^Overlap — /).first()).toBeVisible();
  await page.getByRole("link", { name: "Month", exact: true }).click();
  await expect(page).toHaveURL(/view=month/);
  await expect(page.getByRole("link", { name: new RegExp(`QS Fair ${stamp}`) }).first()).toBeVisible();

  // Mobile: one column, no sideways scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // The head: the team calendar, then the manager's own.
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.goto(`/partnership/calendar?view=week&date=${inDays(8)}`);
  await expect(page.getByRole("heading", { name: "Team calendar" })).toBeVisible();
  await page.getByLabel("Employee").selectOption({ label: `E2E Manager ${stamp}` });
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.getByRole("heading", { name: `E2E Manager ${stamp}'s calendar` })).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(`^${visits[0]} — `) })).toBeVisible();

  // N1: the API refuses more than 31 days.
  const wide = await page.request.get(`/api/v1/partnership/calendar?date_from=${inDays(0)}&date_to=${inDays(31)}`);
  expect(wide.status()).toBe(422);

  // Cancel: the owner cancels the fair and it leaves the calendar.
  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.goto(detail);
  await page.getByRole("button", { name: "Cancel event" }).click();
  await page.getByLabel("Why is the event cancelled?").fill("Fair postponed");
  await page.getByRole("button", { name: "Confirm cancel" }).click();
  await expect(page.getByText("Event cancelled.")).toBeVisible();
  await expect(page.getByText("Status: Cancelled")).toBeVisible();
  await page.goto(`/partnership/calendar?view=week&date=${inDays(8)}`);
  await expect(page.getByRole("link", { name: new RegExp(`QS Fair ${stamp}`) })).toHaveCount(0);
  await expect(page.getByText(/^Overlap — /)).toHaveCount(0);
});
