import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-022 (AC1, AC2, AC5, AC9; G2-G4): a telecaller manager sets an IT team default and an override for their telecaller from a future
// date; the telecaller sees "My targets" on the dashboard and cannot write. Team defaults are shared by the whole database, so the
// team-default write uses a stamped far-future date; assertions on today are about the override, which is this run's own.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function accounts(page: Page, stamp: number) {
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Tgt Manager ${stamp}`, email: `tel022-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Tgt Telecaller ${stamp}`, email: `tel022-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `TG-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const istToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
const plusDays = (iso: string, n: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

test("manager sets a team default and an override; the telecaller sees My targets and cannot write", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const { manager, caller } = await accounts(page, stamp);
  const tomorrow = plusDays(istToday(), 1);
  const farDay = plusDays("2200-01-01", stamp % 30000);

  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.getByRole("link", { name: "Targets" }).first().click();
  await page.waitForURL("**/telecaller/manager/targets");
  await expect(page.getByRole("region", { name: "Targets in effect" })).toBeVisible();

  // IT team default: Calls/day 80 from a far-future day (G2: any date from tomorrow on).
  await expect(page.getByLabel("Starts on")).toHaveValue(tomorrow);
  await page.getByLabel("Starts on").fill(farDay);
  await page.getByLabel("Calls target", { exact: true }).fill("80");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByText(/Saved 1 target from/)).toBeVisible();
  const team = await (await page.request.get(`/api/v1/telecaller/targets/effective?team=it&date=${farDay}`)).json();
  expect(team.daily.find((r: { kpi: string }) => r.kpi === "calls")).toEqual({ kpi: "calls", value: 80, source: "team" });

  // A past date is refused by the API with a sentence (the browser's min is bypassed on purpose).
  await page.getByLabel("Starts on").fill(istToday());
  await page.getByLabel("Calls target", { exact: true }).fill("81");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByText(/Daily targets can start on .* or later/)).toBeVisible();

  // The override for my telecaller: Calls/day 90 from tomorrow (AC1, AC2: today keeps its value).
  await page.getByLabel("Set targets for").selectOption("user");
  const picker = page.getByRole("combobox", { name: /Telecaller/ });
  await picker.fill(`E2E Tgt Telecaller ${stamp}`);
  await page.getByRole("option", { name: new RegExp(`E2E Tgt Telecaller ${stamp}`) }).click();
  await expect(page.getByRole("region", { name: "Targets in effect" })).toBeVisible();
  await page.getByLabel("Starts on").fill(tomorrow);
  await page.getByLabel("Calls target", { exact: true }).fill("90");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByText(/Saved 1 target from/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Target history" }).getByRole("row", { name: /Daily Calls 90/ })).toBeVisible();
  const mine = await (await page.request.get(`/api/v1/telecaller/targets/effective?user_id=${caller.id}&date=${tomorrow}`)).json();
  expect(mine.daily.find((r: { kpi: string }) => r.kpi === "calls")).toEqual({ kpi: "calls", value: 90, source: "user" });
  const now = await (await page.request.get(`/api/v1/telecaller/targets/effective?user_id=${caller.id}`)).json();
  expect(now.daily.find((r: { kpi: string }) => r.kpi === "calls").source).not.toBe("user");

  // Monthly: the start is a month picker of 1sts.
  await page.getByLabel("Monthly").check();
  await expect(page.getByLabel("Starts on")).toHaveValue(/^\d{4}-\d{2}-01$/);

  // Mobile: the page fits a phone width.
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // The telecaller: My targets on the dashboard; a write is 403 (§22).
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  const card = page.getByRole("region", { name: "My targets", exact: true });
  await expect(card).toBeVisible();
  await expect(card.getByRole("row", { name: /^Calls/ })).toBeVisible();
  const write = await page.request.post("/api/v1/telecaller/targets", { data: { scope: "team", team: "it", period: "daily", values: { calls: 1 } } });
  expect(write.status()).toBe(403);
  const other = await page.request.get(`/api/v1/telecaller/targets/effective?user_id=${manager.id}`);
  expect(other.status()).toBe(403);
  await page.goto("/telecaller/manager/targets");
  await expect(page.getByText(/Telecaller manager role required/)).toBeVisible();
  expect(errors.filter((e) => !/403|Forbidden|422/.test(e)) /* the deliberate past-date 422 and the telecaller 403s */).toEqual([]);
});
