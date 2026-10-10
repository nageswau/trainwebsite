import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-022 (§22, §20; spec DB1-DB16): a manager lands on the dashboard and sees their own figures -- the overview groups, this month's
// contact and the expected partnership with its weighted forecast, and follow-up bands that add up to the Tasks list -- and opens a tile's
// list; the head reaches the team's dashboard from the nav; a counselor is refused; the page fits a phone. Throwaway accounts via the real
// admin API.

const istToday = () => new Date(Date.now() + 330 * 60_000).toISOString().slice(0, 10);

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function send(page: Page, method: "post" | "patch", url: string, data: unknown) {
  const response = await page.request[method](url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const head = await send(page, "post", "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc022-h-${stamp}@example.local` });
  const manager = async (n: number) =>
    send(page, "post", "/api/v1/admin/users", {
      role: "partnership_manager", full_name: `E2E Manager ${n} ${stamp}`, email: `upc022-m${n}-${stamp}@example.local`,
      partnership_profile: { employee_id: `U22-${n}-${stamp}`, reporting_head_user_id: head.id },
    });
  const [first, second] = [await manager(1), await manager(2)];
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const university = async (name: string, owner: { id: string }) => {
    const { university: made } = await send(page, "post", "/api/v1/partnership/universities", { name: `${name} ${stamp}`, country_id: countries.items[0].id, city: "London" });
    await send(page, "post", `/api/v1/partnership/universities/${made.id}/assign`, { primary_manager_user_id: owner.id });
    return made;
  };
  const engaged = await university("E2E Dashboard Engaged", first);
  await send(page, "post", `/api/v1/partnership/universities/${engaged.id}/stage`, { to_stage: "interested", from_stage: "target_university" }); // G2, contacted (D6)
  await send(page, "patch", `/api/v1/partnership/universities/${engaged.id}/expected`, { expected_agreement_date: istToday() }); // D13: 40%
  await university("E2E Dashboard Target", first); // G3
  await university("E2E Dashboard Colleague", second); // not the first manager's
  const counselor = await send(page, "post", "/api/v1/admin/users", { role: "counselor", division: "overseas", full_name: `E2E Counselor ${stamp}`, email: `upc022-c-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, first, second, counselor]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, first, engaged, counselor };
}

const region = (page: Page, name: string | RegExp) => page.getByRole("region", { name });
const tile = (page: Page, group: string | RegExp, label: string) =>
  region(page, group).locator(".kpi-tile").filter({ has: page.locator("dt", { hasText: new RegExp(`(^|\\s)${label}$`) }) });
const value = (page: Page, group: string | RegExp, label: string) => tile(page, group, label).locator(".kpi-value");

test("a manager reads their dashboard and the head reads the team's", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, first, engaged, counselor } = await setUp(page, stamp);

  await signIn(page, "/overseas/login", first.email, "/partnership/dashboard");
  await send(page, "post", "/api/v1/partnership/tasks", { university_id: engaged.id, kind: "follow_up", title: "Follow up on proposal", due_on: istToday() });
  await page.reload();
  await expect(page.getByRole("heading", { name: `Welcome, E2E Manager 1 ${stamp}` })).toBeVisible();

  // D1-D4: the manager's two universities, one in progress and one target; never the colleague's.
  const overview = "Global Partnership Overview";
  await expect(value(page, overview, "Total Universities")).toHaveText("2");
  await expect(value(page, overview, "Partnership in Progress")).toHaveText("1");
  await expect(value(page, overview, "Target Universities")).toHaveText("1");
  await expect(value(page, overview, "Active Partners")).toHaveText("0");

  // D6, D13: contacted this month; expected this month at Interested's 40%.
  const month = /^This Month — /;
  await expect(value(page, month, "New universities contacted")).toHaveText("1");
  await expect(value(page, month, "Expected partnerships")).toHaveText("1");
  await expect(tile(page, month, "Expected partnerships")).toContainText("Weighted forecast: 0.4");

  // §20 bands: the same numbers as the Tasks list (the stage move added its own auto-task, so read the counts from the list's API).
  const { counts } = await (await page.request.get("/api/v1/partnership/tasks?band=today&assignee=me")).json();
  expect(counts.today).toBeGreaterThanOrEqual(1);
  for (const [label, band] of [["Overdue", "overdue"], ["Due Today", "today"], ["Due Tomorrow", "tomorrow"], ["Upcoming", "upcoming"]] as const) {
    await expect(value(page, "Follow-ups", label)).toHaveText(String(counts[band]));
  }
  await expect(value(page, month, "Overdue follow-ups")).toHaveText(String(counts.overdue));

  // upc-001 keeps its profile card on the landing page.
  await expect(page.locator("dd", { hasText: `U22-1-${stamp}` })).toBeVisible();

  // A tile opens its list.
  await region(page, "Follow-ups").getByRole("link", { name: "View due today" }).click();
  await page.waitForURL("**/partnership/tasks?band=today");
  await expect(page.getByText("Follow up on proposal").first()).toBeVisible();

  // Phone width: no horizontal scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/partnership/dashboard");
  await expect(region(page, overview)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // The head: Dashboard in the nav, the team's figures (both managers' universities + unowned ones).
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.getByRole("navigation").getByRole("link", { name: "Dashboard", exact: true }).first().click();
  await page.waitForURL("**/partnership/dashboard");
  await expect(page.getByText(/Your team's universities/)).toBeVisible();
  expect(Number(await value(page, overview, "Total Universities").textContent())).toBeGreaterThanOrEqual(3);
  await expect(page.getByRole("heading", { name: "Coming soon to your CRM" })).toHaveCount(0);

  // A counselor is refused by the API and the page.
  await signIn(page, "/overseas/login", counselor.email, "/overseas/counselor/dashboard");
  expect((await page.request.get("/api/v1/partnership/dashboard")).status()).toBe(403);
  await page.goto("/partnership/dashboard");
  await expect(page.getByText("The partnership dashboard is for partnership managers and heads")).toBeVisible();
});
