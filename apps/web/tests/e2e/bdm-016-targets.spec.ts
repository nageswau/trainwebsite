import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-016 (AC2, AC4, AC5, R5, R8): a College BDM contacts a college; the manager opens Targets, sets Colleges Contacted 4 and sees
// achieved 1 and 25%; a KPI outside the type is refused; last month is read-only; the BDM sees the target on My Day; Copy fills next
// month. Nothing overflows at 320 / 375 px.
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

const shift = (month: string, by: number) => {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + by;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
};

test("BDM monthly targets: set, achieved and percent, read-only past, My Day card, copy", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  const month = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }).slice(0, 7); // the IST month
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm016-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm016-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E16-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await expect(page.getByText("No targets set for this month yet.")).toBeVisible();
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  })).json()).organization;
  expect((await page.request.post("/api/v1/bdm/activities", {
    data: { organization_id: org.id, channel: "call", direction: "outbound", occurred_at: new Date(Date.now() - 60_000).toISOString() },
  })).status()).toBe(201);
  expect((await page.request.get("/api/v1/bdm/manager/targets")).status()).toBe(403);

  // The manager's team list, then the BDM's sheet.
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.getByRole("link", { name: "Targets", exact: true }).first().click();
  await page.waitForURL("**/bdm/manager/targets");
  const row = page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(`E2E BDM ${stamp}`) }) });
  await expect(row.getByRole("cell").first()).toHaveText("0 of 14");
  await noOverflow(page);
  await row.getByRole("link", { name: `Set targets for E2E BDM ${stamp}` }).click();
  await page.waitForURL(`**/bdm/manager/targets/${bdm.id}?month=${month}`);

  // AC5: Colleges Contacted 4, achieved 1 → 25%.
  await page.getByLabel("Colleges Contacted target").fill("4");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved 1 target." })).toBeVisible();
  const kpi = page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: /^Colleges Contacted/ }) });
  await expect(kpi.getByRole("cell").nth(1)).toHaveText("1");
  await expect(kpi.getByRole("cell").nth(2)).toHaveText("25%");
  await expect(page.getByRole("rowheader", { name: /^Internship Students/ }).locator("xpath=..").getByRole("cell").nth(1)).toHaveText("Not tracked");
  await page.reload();
  await expect(page.getByLabel("Colleges Contacted target")).toHaveValue("4");
  await noOverflow(page);

  // AC2: a KPI outside the College catalogue is refused by name; AC4: last month is read-only for a manager.
  const wrong = await page.request.put("/api/v1/bdm/manager/targets", { data: { month, items: [{ bdm_user_id: bdm.id, kpi_key: "active_schools", target: 2 }] } });
  expect(wrong.status()).toBe(422);
  expect(await wrong.text()).toContain("Active Schools is not a target KPI for College BDMs");
  await page.goto(`/bdm/manager/targets/${bdm.id}?month=${shift(month, -1)}`);
  await expect(page.getByText("Past months are read-only.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save targets" })).toHaveCount(0);

  // R8: copy this month's target into next month.
  await page.goto(`/bdm/manager/targets?month=${shift(month, 1)}`);
  await page.getByRole("button", { name: "Copy last month's targets" }).click();
  await page.getByRole("button", { name: "Yes, copy" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Copied 1 target." })).toBeVisible();
  await expect(row.getByRole("cell").first()).toHaveText("1 of 14");

  // The BDM's My Day card.
  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await expect(page.getByRole("region", { name: /^Monthly targets/ }).getByText("Colleges Contacted — 1 / 4 (25%)")).toBeVisible();
  await noOverflow(page);
});
