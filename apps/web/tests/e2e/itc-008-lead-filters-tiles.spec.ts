import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-008: a telecaller with three website leads calls two of them today (one reached). My Leads narrows by source and by last-contact
// day, and the filters survive a reload (AC1); a reversed range says so. The dashboard's Contact Rate / Qualified / Handovers tiles
// equal the manager's Telecaller Report row for today (AC2).

const IST_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" });
const today = () => IST_DAY.format(new Date());

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Itc8 Manager ${stamp}`, email: `itc008-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Itc8 Telecaller ${stamp}`, email: `itc008-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `I8-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const leads: string[] = [];
  for (const i of [0, 1, 2]) {
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name: `Itc8 Lead ${i} ${stamp}`, email: `itc008-${i}-${stamp}@example.com`, phone: `7${String(stamp).slice(-8)}${i}`, subject: "Python", message: "Call me." },
    });
    expect(created.status()).toBe(201);
    leads.push((await created.json()).id);
  }
  expect((await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads, telecaller_user_id: caller.id } })).status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, leads };
}

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

const tile = (page: Page, label: string) =>
  page.getByRole("list", { name: "Today at a glance" }).getByRole("listitem").filter({ has: page.getByText(label, { exact: true }) });

test("lead list filters round-trip through the URL and the new tiles equal the Telecaller Report", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const { manager, caller, leads } = await setup(page, stamp);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await signIn(page, "it", caller.email);
  for (const [id, outcome] of [[leads[0], "interested"], [leads[1], "busy"]]) {
    const logged = await page.request.post(`/api/v1/telecaller/leads/${id}/calls`, { data: { duration_seconds: 30, call_type: "outgoing", outcome } });
    expect(logged.status()).toBe(201);
  }

  // AC1: source + last contact today, by URL, kept on reload
  await page.goto(`/telecaller/leads?q=${stamp}`);
  await expect(page.getByRole("link", { name: `Itc8 Lead 2 ${stamp}` })).toBeVisible();
  await page.getByLabel("Source").selectOption("website");
  await expect(page).toHaveURL(/source=website/);
  await page.getByLabel("Last contact from").fill(today());
  await page.getByLabel("Last contact to").fill(today()); // QA8-01: at once, before the URL catches up -- both must stay
  await expect(page).toHaveURL(new RegExp(`last_contact_to=${today()}`));
  await expect(page.getByRole("link", { name: `Itc8 Lead 2 ${stamp}` })).toHaveCount(0);
  await expect(page.getByRole("link", { name: `Itc8 Lead 0 ${stamp}` })).toBeVisible();
  await expect(page.getByRole("link", { name: `Itc8 Lead 1 ${stamp}` })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Source")).toHaveValue("website");
  await expect(page.getByLabel("Last contact from")).toHaveValue(today());
  await expect(page.getByRole("link", { name: `Itc8 Lead 2 ${stamp}` })).toHaveCount(0);
  await page.getByLabel("Source").selectOption("instagram");
  await expect(page.getByText("No leads match these filters.")).toBeVisible();

  // a reversed next-follow-up range is refused on the page, without a request
  await page.goto(`/telecaller/leads?next_follow_up_from=2026-11-05&next_follow_up_to=2026-11-04`);
  await expect(page.locator(".form-error")).toHaveText("Choose a start date on or before the end date.");

  // AC2: the tiles ...
  await page.goto("/telecaller/dashboard");
  await expect(tile(page, "Contact Rate")).toContainText("50.0%");
  await expect(tile(page, "Qualified")).toContainText("0");
  await expect(tile(page, "Handovers")).toContainText("0");

  // ... equal the manager's report row for the same day
  await page.request.post("/api/v1/auth/logout");
  await page.context().clearCookies();
  await signIn(page, "admin", manager.email);
  await page.goto(`/telecaller/manager/reports?report=telecaller&date_from=${today()}&date_to=${today()}`);
  const row = page.getByRole("row").filter({ hasText: `E2E Itc8 Telecaller ${stamp}` });
  await expect(row.locator('[data-label="Contact rate (%)"]')).toHaveText("50.0");
  await expect(row.locator('[data-label="Handovers"]')).toHaveText("0");
  await expect(row.locator('[data-label="Qualified"]')).toHaveText("0");
  expect(errors).toEqual([]);
});
