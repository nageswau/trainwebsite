import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-009 (AC1, AC3, AC4, AC6, AC12): a College BDM logs a call and a visit on an organization, sees them on the timeline and in the day
// counts, edits and deletes one; the manager sees the team's day; keyboard-only logging; nothing overflows at 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) { // §12.2 F9
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("BDM activity log: log, timeline, counts, edit, delete, manager view", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm009-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm009-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E9-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  });
  const org = (await created.json()).organization;

  // AC1 + AC6: log a call on the profile; it shows on the timeline.
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Log activity" }).click();
  await page.getByLabel("Outgoing", { exact: true }).check();
  await page.getByLabel("Contact", { exact: true }).selectOption({ label: "Dr Rao" });
  await page.getByLabel("Note", { exact: true }).fill("Discussed the MoU");
  await page.getByRole("button", { name: "Save activity" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Activity logged." })).toBeVisible();
  const timeline = page.getByRole("list", { name: "Activity" });
  await expect(timeline.getByText("Call · Outgoing")).toBeVisible();
  await expect(timeline.getByText("Discussed the MoU")).toBeVisible();

  // a visit, keyboard only (AC12)
  await page.getByRole("button", { name: "Log activity" }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Channel (required)").focus();
  await page.getByLabel("Channel (required)").selectOption("visit"); // a focused native select, as the keyboard would set it
  await page.getByRole("button", { name: "Save activity" }).focus();
  await page.keyboard.press("Enter");
  await expect(timeline.getByText("Visit", { exact: true })).toBeVisible();

  // AC3: the day's counts
  await page.getByRole("link", { name: "Activities" }).first().click();
  await page.waitForURL("**/bdm/activities");
  const counts = page.getByLabel("Day counts");
  await expect(counts.getByText("Call", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("1");
  await expect(counts.getByText("Visit", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("1");
  await expect(counts.getByText("Organizations contacted").locator("xpath=following-sibling::dd")).toHaveText("1");

  // AC4: edit today's call, delete the visit; counts follow
  const list = page.getByRole("list", { name: "Activities" });
  await list.getByRole("listitem").filter({ hasText: "Call" }).getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Note", { exact: true }).fill("MoU draft next week");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(list.getByText("MoU draft next week")).toBeVisible();
  await list.getByRole("listitem").filter({ hasText: "Visit" }).getByRole("button", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(counts.getByText("Visit", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("0");

  await noOverflow(page);
  await page.goto(`/bdm/organizations/${org.id}`);
  await noOverflow(page);

  // the manager sees the team's day
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/activities");
  await expect(page.getByRole("list", { name: "Activities" }).getByText("MoU draft next week")).toBeVisible();
  await expect(page.getByRole("button", { name: /Edit|Delete|Log activity/ })).toHaveCount(0);
  await noOverflow(page);
});
