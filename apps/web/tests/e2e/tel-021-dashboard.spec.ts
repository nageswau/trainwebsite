import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-021 (DEC-SCOPE-103): a telecaller with two leads assigned today logs a not-connected call; the dashboard's tiles, target progress
// and daily activity show it, an earlier day is all zeros, a future day is refused. The manager opens the report's activity from the
// Team table; another manager's telecaller reads as "not one of your reports".

const IST_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" });
const istDay = (offsetDays: number) => IST_DAY.format(new Date(Date.now() + offsetDays * 86_400_000));
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function account(page: Page, stamp: string, managerId?: string) {
  const manager = managerId ?? (await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Dash Manager ${stamp}`, email: `tel021-m-${stamp}@example.local` },
  })).json());
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Dash Telecaller ${stamp}`, email: `tel021-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `DB-${stamp}`, reporting_manager_user_id: typeof manager === "string" ? manager : manager.id },
    },
  })).json();
  return { manager, caller };
}

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const { manager, caller } = await account(page, String(stamp));
  const { caller: stranger } = await account(page, `${stamp}x`);
  const leads: string[] = [];
  for (const i of [0, 1]) {
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name: `Dash Lead ${i} ${stamp}`, email: `tel021-${i}-${stamp}@example.com`, phone: `6${String(stamp).slice(-8)}${i}`, subject: "Python", message: "Call me." },
    });
    expect(created.status()).toBe(201);
    leads.push((await created.json()).id);
  }
  expect((await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads, telecaller_user_id: caller.id } })).status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, stranger, leads };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const tile = (page: Page, label: string) => page.getByRole("list", { name: "Today at a glance" }).getByRole("listitem").filter({ hasText: label });
const count = (page: Page, label: string) => page.getByRole("region", { name: "Activity counts" }).getByRole("row", { name: new RegExp(`^${label} `) });

test("the telecaller's dashboard and daily activity, and the manager's view of a report", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const { manager, caller, stranger, leads } = await setup(page, stamp);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  const logged = await page.request.post(`/api/v1/telecaller/leads/${leads[0]}/calls`, { data: { duration_seconds: 0, call_type: "outgoing", outcome: "busy" } });
  expect(logged.status()).toBe(201);
  await page.reload();

  // §1 tiles (B1, B2, B7, B10): both leads arrived today; one call made, two leads still to call.
  await expect(tile(page, "New Leads")).toContainText("2");
  await expect(tile(page, "Calls Today")).toContainText("1 / 2");
  await expect(tile(page, "Not Connected")).toContainText("1");
  await expect(tile(page, "Converted")).toContainText("0");
  await expect(tile(page, "Daily Target")).toContainText(/1 \/ (\d+|not set)/);
  // §15 achieved / target, today and the month to date.
  await expect(page.getByRole("region", { name: "My targets", exact: true }).getByRole("row", { name: /^Calls/ })).toContainText(/1 \/ .*1 \/ /);
  await expect(page.getByText("No appointments today.")).toBeVisible();
  // §14 daily activity for today, then yesterday (zeros, not "no data"), then a refused future day.
  await expect(count(page, "Total calls")).toContainText("1");
  await expect(count(page, "Not connected")).toContainText("1");
  await expect(count(page, "Total leads assigned")).toContainText("2");
  await page.getByLabel("Day").fill(istDay(-1));
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForURL(`**/telecaller/dashboard?date=${istDay(-1)}`);
  await expect(count(page, "Total calls")).toContainText("0");
  await expect(count(page, "Total leads assigned")).toContainText("0");
  await page.goto(`/telecaller/dashboard?date=${istDay(2)}`);
  await expect(page.getByRole("alert")).toContainText("can't be shown for a future date");
  // Another user's activity is refused (403).
  expect((await page.request.get(`/api/v1/telecaller/activity?user_id=${manager.id}`)).status()).toBe(403);

  // Tablet and phone: no sideways scroll.
  for (const width of [820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/telecaller/dashboard");
    await expect(tile(page, "Overdue")).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // The manager: Team -> the report's activity (DB6); another manager's telecaller is not theirs.
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.getByRole("link", { name: `Activity for E2E Dash Telecaller ${stamp}` }).click();
  await page.waitForURL(`**/telecaller/manager/team/${caller.id}/activity`);
  await expect(page.getByRole("heading", { name: `E2E Dash Telecaller ${stamp}` })).toBeVisible();
  await expect(count(page, "Total calls")).toContainText("1");
  await page.goto(`/telecaller/manager/team/${stranger.id}/activity`);
  await expect(page.getByText("This telecaller is not one of your reports.")).toBeVisible();
  expect(errors.filter((e) => !/403|404|422|Forbidden|Not Found|Unprocessable/.test(e))).toEqual([]);
});
