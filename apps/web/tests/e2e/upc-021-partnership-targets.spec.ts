import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-021 (AC1, AC3, AC4, AC6, AC8): the head opens Targets & Forecast from the menu, sets a manager's monthly targets (an invalid value is
// refused in place), and the comparison shows actual / target with the team row; the manager's Proposal Sent move counts as an actual;
// the manager sees their own month read-only and cannot reach a peer's; the pages fit a phone. Throwaway accounts via the real admin API.

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

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc021-h-${stamp}@example.local` });
  const manager = async (n: number) =>
    post("/api/v1/admin/users", {
      role: "partnership_manager", full_name: `E2E Manager ${n} ${stamp}`, email: `upc021-m${n}-${stamp}@example.local`,
      partnership_profile: { employee_id: `U21-${n}-${stamp}`, reporting_head_user_id: head.id },
    });
  const [first, second] = [await manager(1), await manager(2)];
  first.full_name = `E2E Manager 1 ${stamp}`; // the create response carries no name
  second.full_name = `E2E Manager 2 ${stamp}`;
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Targets University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: first.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, first, second]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, first, second, university };
}

test("the head sets targets, the comparison counts actuals, the manager reads their own month", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, first, second, university } = await setUp(page, stamp);

  // The manager moves their university to Proposal Sent: one Proposals actual this month.
  await signIn(page, "/overseas/login", first.email, "/partnership/dashboard");
  await page.goto(`/partnership/universities/${university.id}`);
  await page.getByLabel("Move to").selectOption("proposal_sent");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.getByText("Moved to Proposal Sent")).toBeVisible();

  // AC3: the head opens the menu entry, sees both reports, and sets the first manager's targets.
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.getByRole("link", { name: "Targets & Forecast" }).first().click();
  await expect(page.getByRole("heading", { name: /^Team targets — / })).toBeVisible();
  const table = page.getByRole("region", { name: /Actual \/ target and achievement by manager/ });
  await expect(table.getByRole("rowheader", { name: first.full_name })).toBeVisible();
  await expect(table.getByRole("rowheader", { name: second.full_name })).toBeVisible();
  await page.getByRole("link", { name: `Set targets for ${first.full_name}` }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^${first.full_name} — `) })).toBeVisible();
  await page.getByLabel("Proposals target").fill("4.5");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Proposals target must be a whole number from 0 to 100000.");
  await page.getByLabel("Proposals target").fill("4");
  await page.getByLabel("MoUs target").fill("2");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved 2 targets." })).toBeVisible();
  const proposals = page.getByRole("rowheader", { name: /^Proposals/ }).locator("xpath=..");
  await expect(proposals).toContainText("1");
  await expect(proposals).toContainText("25%");
  await expect(page.getByRole("rowheader", { name: /^Meetings/ }).locator("xpath=..")).not.toContainText("Not tracked"); // TG13: upc-009 meetings count

  // AC6: back on the comparison, the manager's row and the team row read actual / target · achievement.
  await page.getByRole("link", { name: "All team targets" }).click();
  await expect(table.getByRole("rowheader", { name: first.full_name }).locator("xpath=..")).toContainText("1 / 4 · 25%");
  await expect(table.getByRole("rowheader", { name: "Team" }).locator("xpath=..")).toContainText("1 / 4 · 25%");

  // AC8: a phone keeps the page usable -- the wide table scrolls inside its region, the page itself does not scroll sideways.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);

  // AC4: the manager sees their own month read-only, and a peer's month is not theirs to see.
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, "/overseas/login", first.email, "/partnership/dashboard");
  await page.getByRole("link", { name: "Targets & Forecast" }).first().click();
  await expect(page.getByRole("heading", { name: /^My targets — / })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: /^Proposals/ }).locator("xpath=..")).toContainText("4");
  await expect(page.getByRole("button", { name: "Save targets" })).toHaveCount(0);
  await page.goto(`/partnership/targets/${second.id}`);
  await expect(page.getByText("Partnership manager not found")).toBeVisible();
});
