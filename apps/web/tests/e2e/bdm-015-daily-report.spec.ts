import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-015 (AC1-AC4, R5, R7): a College BDM logs a call, sees it in the daily report, submits with a note; the day's activities lock;
// the manager's grid shows Submitted for one BDM and Missing for the other; the manager opens the report and comments; the BDM reads
// the comment. Nothing overflows at 320 / 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "overseas" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

const tile = (page: Page, label: string) => page.getByLabel("Day counts").getByText(label, { exact: true }).locator("xpath=following-sibling::dd[1]");

test("BDM daily report: preview, submit, lock, manager grid and comment", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm015-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm015-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E15-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  const quiet = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E Quiet ${stamp}`, email: `bdm015-q-${stamp}@example.local`,
            bdm_profile: { bdm_type: "school", employee_id: `E2E15Q-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm, quiet]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  })).json()).organization;
  const call = await (await page.request.post("/api/v1/bdm/activities", {
    data: { organization_id: org.id, channel: "call", direction: "outbound", occurred_at: new Date(Date.now() - 60_000).toISOString() },
  })).json();

  // AC1: the live preview counts the call; untracked counts are labelled (a College report has none).
  await page.getByRole("link", { name: "Daily report" }).first().click();
  await page.waitForURL("**/bdm/daily-report");
  await expect(tile(page, "Calls made")).toHaveText("1");
  await expect(tile(page, "Colleges contacted")).toHaveText("1");
  await expect(tile(page, "Meetings completed")).toHaveText("0");
  await noOverflow(page);

  // Submit with a note, after the confirm.
  await page.getByLabel("End-of-day note (optional)").fill("Visited Kochi colleges");
  await page.getByRole("button", { name: "Submit report" }).click();
  await page.getByRole("button", { name: "Yes, submit" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Report submitted." })).toBeVisible();
  await expect(page.getByText("Visited Kochi colleges")).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit report" })).toHaveCount(0);

  // AC2 + R5: a second submit is 409; the day's activities are locked.
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }); // the IST day, YYYY-MM-DD
  expect((await page.request.post(`/api/v1/bdm/daily-reports/${today}/submit`, { data: {} })).status()).toBe(409);
  expect((await page.request.patch(`/api/v1/bdm/activities/${call.id}`, { data: { note: "late edit" } })).status()).toBe(409);
  await page.goto("/bdm/activities");
  await expect(page.getByRole("list", { name: "Activities" }).getByRole("button", { name: "Edit" })).toHaveCount(0);

  // AC4: the manager sees Submitted for the BDM, Missing for the quiet one; opens the report and comments.
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/daily-reports");
  const rowOf = (name: string) => page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(name) }) });
  await expect(rowOf(`E2E BDM ${stamp}`).getByRole("cell").first()).toContainText("Submitted"); // today is the first column (QA15-02)
  await expect(rowOf(`E2E Quiet ${stamp}`).getByRole("cell").first()).toHaveText("Missing");
  await noOverflow(page);
  await rowOf(`E2E BDM ${stamp}`).getByRole("cell").first().getByRole("link").click();
  await page.waitForURL(`**/bdm/manager/daily-reports/${bdm.id}?date=${today}`);
  await expect(tile(page, "Calls made")).toHaveText("1");
  await page.getByLabel("Your comment").fill("Good coverage");
  await page.getByRole("button", { name: "Save comment" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Comment saved." })).toBeVisible();
  await noOverflow(page);

  // The BDM reads the comment.
  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto("/bdm/daily-report");
  await expect(page.getByText("Good coverage")).toBeVisible();
});
