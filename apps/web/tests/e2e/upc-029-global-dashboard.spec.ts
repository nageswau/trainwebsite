import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-029 (§31; spec GD1-GD17): a partnership head opens the Global Dashboard from the nav and sees the three columns, whose counts equal
// their upc-022 dashboard's overview (the shared database holds other tests' unowned universities, so the head's figures are compared, not
// fixed), the Management §19 pipeline, the funnel and the commission; a column heading opens its pipeline column; a manager is refused;
// the page fits a phone. Throwaway accounts via the real admin API.

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
  const head = await send(page, "post", "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc029-h-${stamp}@example.local` });
  const manager = await send(page, "post", "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc029-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U29-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const university = async (name: string) => {
    const { university: made } = await send(page, "post", "/api/v1/partnership/universities", { name: `${name} ${stamp}`, country_id: countries.items[0].id, city: "London" });
    await send(page, "post", `/api/v1/partnership/universities/${made.id}/assign`, { primary_manager_user_id: manager.id });
    return made;
  };
  const engaged = await university("E2E Global Engaged");
  await send(page, "post", `/api/v1/partnership/universities/${engaged.id}/stage`, { to_stage: "interested", from_stage: "target_university" }); // G2
  await send(page, "patch", `/api/v1/partnership/universities/${engaged.id}/expected`, { expected_agreement_date: istToday() });
  await university("E2E Global Target"); // G3
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager };
}

const columnCount = async (page: Page, title: string) => {
  const text = await page.getByRole("heading", { level: 3, name: new RegExp(`^${title} \\(\\d+\\)$`) }).innerText();
  return Number(/\((\d+)\)/.exec(text)![1]);
};

test("a head reads the global dashboard, and it reconciles with their dashboard", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, manager } = await setUp(page, stamp);

  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.getByRole("navigation").getByRole("link", { name: "Global Dashboard", exact: true }).first().click();
  await page.waitForURL("**/partnership/head/global-dashboard");
  await expect(page.getByRole("heading", { level: 2, name: /EduSphere Global Partnerships/ })).toBeVisible();

  const overview = (await (await page.request.get("/api/v1/partnership/dashboard")).json()).overview;
  expect(await columnCount(page, "Active Partners")).toBe(overview.partners);
  expect(await columnCount(page, "In Progress")).toBe(overview.in_progress);
  expect(await columnCount(page, "Target List")).toBe(overview.targets);
  expect(overview.in_progress).toBeGreaterThanOrEqual(1);
  const progress = page.getByRole("region", { name: /^In Progress/ });
  await expect(progress.getByRole("table", { name: "Expected agreement date" })).toBeVisible();
  await expect(progress.getByText(/^Weighted forecast: /)).toBeVisible();
  await expect(page.getByRole("region", { name: "Target List" + ` (${overview.targets})` }).getByRole("table", { name: "Priority" })).toBeVisible();

  const pipeline = page.getByRole("region", { name: "Partnership Pipeline" });
  await expect(pipeline.locator(".kpi-tile")).toHaveCount(8);
  await expect(page.getByRole("list", { name: /^Student recruitment/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "University Commission" })).toBeVisible(); // U2: a head sees commission

  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  const scrolls = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(scrolls).toBe(false);
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.getByRole("link", { name: /^Target List \(\d+\)$/ }).click();
  await page.waitForURL("**/partnership/pipeline?column=target");

  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.goto("/partnership/head/global-dashboard");
  await expect(page.getByText("The global partnership dashboard is for partnership heads and super admins")).toBeVisible();
});
