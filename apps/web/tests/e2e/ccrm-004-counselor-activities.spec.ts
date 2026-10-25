import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-004 (DEC-SCOPE-259 LG1, LG3): the counselor a lead is handed to logs a call (no stage effect) and records a meeting; both show in
// the Activity timeline; the telecaller sees the call read only; another counselor is 404. Throwaway accounts; phone width has no
// sideways scroll.
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("the counselor logs a call and records a meeting on their lead", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E AC Manager ${stamp}`, email: `ccrm004-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E AC Telecaller ${stamp}`, email: `ccrm004-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `AC-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E AC Counselor ${stamp}`;
  const counselor = await post({ role: "counselor", division: "it", full_name: counselorName, email: `ccrm004-c-${stamp}@example.local` });
  const other = await post({ role: "counselor", division: "it", full_name: `E2E AC Other ${stamp}`, email: `ccrm004-o-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [caller, counselor, other]) await activateWithToken(page.request, user.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the telecaller creates the lead and hands it over
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name: `AC Lead ${stamp}`, email: `ccrm004-l-${stamp}@example.local`, phone, product_id: products[0].id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  await page.goto(`/telecaller/leads/${id}`);
  await page.getByRole("button", { name: "Assign to counselor" }).click();
  await page.getByLabel("Counselor", { exact: true }).selectOption({ label: counselorName });
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByRole("note")).toContainText("You can view it but not change it.");

  // the counselor logs a closing-outcome call: no close note, and the stage stays
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/leads/${id}`);
  const stageLine = page.getByText(/^Stage:/).first();
  const stageBefore = await stageLine.textContent();
  const calls = page.getByRole("region", { name: "Calls" });
  await calls.getByRole("button", { name: "Log call" }).click();
  await calls.getByLabel("Outcome (required)").selectOption("not_interested");
  await expect(calls.getByText(/closes the lead/)).toHaveCount(0);
  await calls.getByLabel("Minutes").fill("4");
  await calls.getByLabel("Remarks").fill("Wants to think it over");
  await calls.getByRole("button", { name: "Save call" }).click();
  await expect(calls.getByText("Call logged.")).toBeVisible();
  await expect(calls.getByRole("list", { name: "Calls" })).toContainText("Wants to think it over");
  await expect(stageLine).toHaveText(stageBefore ?? "");

  // ...and records a meeting
  const meetings = page.getByRole("region", { name: "Meetings" });
  await meetings.getByRole("button", { name: "Record meeting" }).click();
  await meetings.getByLabel("Mode").selectOption("Online");
  await meetings.getByLabel("Notes (required)").fill("Walked through the course plan");
  await meetings.getByRole("button", { name: "Save meeting" }).click();
  await expect(meetings.getByText("Meeting recorded.")).toBeVisible();
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity.getByRole("listitem").filter({ hasText: "Walked through the course plan" })).toContainText("Online meeting");
  await expect(activity.getByRole("listitem").filter({ hasText: "Wants to think it over" })).toContainText(counselorName);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // the telecaller reads the counselor's call, read only
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${id}`);
  const telecallerCalls = page.getByRole("region", { name: "Calls" });
  await expect(telecallerCalls).toContainText("Wants to think it over");
  await expect(telecallerCalls.getByRole("button", { name: "Edit" })).toHaveCount(0);

  // another counselor: 404 for calls and meetings
  await signIn(page, "it", other.email, E2E_PASSWORD, "/it/counselor/dashboard");
  expect((await page.request.get(`/api/v1/counselor/leads/${id}/calls`)).status()).toBe(404);
  expect((await page.request.post(`/api/v1/counselor/leads/${id}/meetings`, { data: { occurred_at: new Date().toISOString(), mode: "Phone", notes: "x" } })).status()).toBe(404);

  expect(consoleErrors).toEqual([]);
});
