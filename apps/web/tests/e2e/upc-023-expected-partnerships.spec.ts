import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-023 (§23-§24; AC1, AC2, EX2-EX6): a manager overrides their university's probability (a missing reason is refused in place), opens
// the forecast from Targets & Forecast and sees only their own universities in the Expected list, with the undated one listed apart; the
// head sees the team's; the page fits a phone. Throwaway accounts via the real admin API.

const istToday = () => new Date(Date.now() + 330 * 60_000).toISOString().slice(0, 10);
const nextMonthStart = (day: string) => {
  const [y, m] = day.split("-").map(Number);
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
};

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
  const send = async (method: "post" | "patch", url: string, data: unknown) => {
    const response = await page.request[method](url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await send("post", "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc023-h-${stamp}@example.local` });
  const manager = async (n: number) =>
    send("post", "/api/v1/admin/users", {
      role: "partnership_manager", full_name: `E2E Manager ${n} ${stamp}`, email: `upc023-m${n}-${stamp}@example.local`,
      partnership_profile: { employee_id: `U23-${n}-${stamp}`, reporting_head_user_id: head.id },
    });
  const [first, second] = [await manager(1), await manager(2)];
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const university = async (name: string, owner: { id: string }, expected: string | null) => {
    const { university: made } = await send("post", "/api/v1/partnership/universities", { name: `${name} ${stamp}`, country_id: countries.items[0].id, city: "London" });
    await send("post", `/api/v1/partnership/universities/${made.id}/assign`, { primary_manager_user_id: owner.id });
    await send("post", `/api/v1/partnership/universities/${made.id}/stage`, { to_stage: "interested", from_stage: "target_university" });
    if (expected) await send("patch", `/api/v1/partnership/universities/${made.id}/expected`, { expected_agreement_date: expected });
    return made;
  };
  const today = istToday();
  const mine = await university("E2E Expected Mine", first, today);
  const undated = await university("E2E Expected Undated", first, null);
  const theirs = await university("E2E Expected Theirs", second, nextMonthStart(today));
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, first, second]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, first, mine, undated, theirs };
}

test("a manager overrides a probability and reads their forecast; the head sees the team's", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, first, mine, undated, theirs } = await setUp(page, stamp);

  // EX2: the owner overrides Interested (40%) to 80%; a missing reason is refused on its field.
  await signIn(page, "/overseas/login", first.email, "/partnership/dashboard");
  await page.goto(`/partnership/universities/${mine.id}`);
  await expect(page.getByText("40%", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Override probability" }).click();
  await page.getByLabel("Probability (%)").fill("80");
  await page.getByRole("button", { name: "Save probability" }).click();
  await expect(page.getByText("Give a reason for the probability override")).toBeVisible();
  await page.getByLabel("Reason").fill("Dean confirmed the budget");
  await page.getByRole("button", { name: "Save probability" }).click();
  await expect(page.getByText("Probability saved.")).toBeVisible();
  await expect(page.getByText("80% (override; stage 40%)")).toBeVisible();

  // The forecast half of Targets & Forecast, then the dedicated list (own scope only).
  await page.goto("/partnership/targets");
  await expect(page.getByRole("heading", { name: "Partnership forecast" })).toBeVisible();
  const month = page.locator(".kpi-tile").filter({ hasText: "Expected Partnerships This Month" });
  await expect(month.locator(".kpi-value")).toHaveText("1");
  await expect(month).toContainText("Weighted forecast: 0.8");
  await page.getByRole("link", { name: "All expected partnerships" }).click();
  await expect(page.getByRole("heading", { name: "Expected University Partnerships" })).toBeVisible();
  const table = page.getByRole("region", { name: /Expected university partnerships/ });
  const row = table.getByRole("row").filter({ hasText: mine.name });
  await expect(row).toContainText("Interested");
  await expect(row).toContainText(first.full_name ?? `E2E Manager 1 ${stamp}`);
  await expect(row).toContainText("80% (override; stage 40%)");
  await expect(row).toContainText("Dean confirmed the budget");
  await expect(table.getByText(theirs.name)).toHaveCount(0);
  await page.getByRole("link", { name: "No expected date (1)" }).click();
  await expect(page).toHaveURL(/window=undated/);
  await expect(page.getByRole("region", { name: /No expected date/ }).getByText(undated.name)).toBeVisible();

  // Phone width: the list scrolls inside its region, never the page.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/partnership/expected");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1280, height: 800 });

  // EX6: the head sees both managers' universities.
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.goto("/partnership/expected?window=this_quarter");
  const quarter = page.getByRole("region", { name: /This quarter/ });
  await expect(quarter.getByText(mine.name)).toBeVisible();
  const nextMonthInQuarter = Math.floor((Number(nextMonthStart(istToday()).slice(5, 7)) - 1) / 3) === Math.floor((Number(istToday().slice(5, 7)) - 1) / 3);
  await expect(quarter.getByText(theirs.name)).toHaveCount(nextMonthInQuarter ? 1 : 0);
  await page.goto("/partnership/expected?window=next_month");
  await expect(page.getByRole("region", { name: /Next month/ }).getByText(theirs.name)).toBeVisible();
});
