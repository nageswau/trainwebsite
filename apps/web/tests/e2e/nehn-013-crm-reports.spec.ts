import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// nehn-013 (DEC-SCOPE-299): a manager's campaign with three leads; the telecaller sets a follow-up due in a minute. The manager reads
// the Date-wise report (grouped by day, then month), the Counselor report's empty state, the Follow-up status counts, and -- once the
// follow-up is past due -- the Pending Follow-ups list and its CSV. The pages hold at tablet and phone widths; a telecaller is refused.

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const BASE = "/telecaller/manager/reports";
const istToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()); // YYYY-MM-DD
const istMonth = () => new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Kolkata", month: "long", year: "numeric" }).format(new Date());

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E N13 Manager ${stamp}`, email: `nehn013-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E N13 Telecaller ${stamp}`, email: `nehn013-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `N13-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const product = await (await page.request.post("/api/v1/telecaller/products", { data: { group: "it", name: `E2E N13 Course ${stamp}` } })).json();
  const campaign = await (await page.request.post("/api/v1/telecaller/campaigns", {
    data: { name: `E2E N13 Campaign ${stamp}`, source: "instagram", product_id: product.id, start_date: "2026-01-01" },
  })).json();
  expect(campaign.id).toBeTruthy();
  const leads: string[] = [];
  for (const i of [0, 1, 2]) {
    const created = await page.request.post("/api/v1/telecaller/leads", {
      data: { name: `N13 Lead ${i} ${stamp}`, phone: `8${String(stamp).slice(-8)}${i}`, product_id: product.id, campaign_id: campaign.id, source: "instagram", division: "it" },
    });
    expect(created.status(), await created.text()).toBe(201);
    leads.push((await created.json()).id);
  }
  expect((await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads, telecaller_user_id: caller.id } })).status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, campaign, leads };
}

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const cells = (page: Page, name: string | RegExp) => page.getByRole("table").getByRole("row", { name }).getByRole("cell");
const tab = (page: Page, name: string) => page.getByRole("navigation", { name: "Reports" }).getByRole("link", { name, exact: true }); // not the sidebar

test("a manager reads the date-wise, counselor and follow-up reports; a telecaller is refused", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const { manager, caller, campaign, leads } = await setup(page, stamp);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${page.url()} :: ${m.text().slice(0, 60)}`); });
  page.on("pageerror", (e) => errors.push(e.message));

  // The telecaller sets a follow-up due in 75 seconds (the API refuses a past due time), then is refused the new reports.
  await signIn(page, "it", caller.email);
  const due = new Date(Date.now() + 75_000).toISOString();
  const fu = await page.request.post(`/api/v1/telecaller/leads/${leads[1]}/follow-ups`, { data: { due_at: due, reason: "fee_details" } });
  expect(fu.status(), await fu.text()).toBe(201);
  for (const kind of ["counselor", "date", "follow_ups", "pending_follow_ups"]) {
    expect((await page.request.get(`/api/v1/telecaller/reports/${kind}`)).status()).toBe(403);
  }
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "admin", manager.email);
  const filter = `campaign_id=${campaign.id}`;

  // Date-wise: by day (the default) one row for today, then by month through the form; the grouping stays in the address.
  await page.goto(`${BASE}?report=date&${filter}`);
  await expect(page.getByRole("heading", { name: "Date-wise Report" })).toBeVisible();
  await expect(page.getByLabel("Group by")).toHaveValue("day");
  for (const name of ["Lead Source", "Counselor", "Date-wise", "Follow-up Status", "Pending Follow-ups"]) {
    await expect(tab(page, name)).toBeInViewport({ ratio: 1 }); // QA-02: no tab hidden off the edge at 1280px
  }
  await expect(cells(page, istToday())).toHaveText(["3", "0", "0", "0", "0", "0", "0.0"]);
  await page.getByLabel("Group by").selectOption("month");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/group=month/);
  await expect(cells(page, istMonth())).toHaveText(["3", "0", "0", "0", "0", "0", "0.0"]);
  await expect(page.getByRole("table").getByRole("columnheader")).toHaveText(
    ["Period", "Leads", "Connected", "Qualified", "Counselling", "Enrolled", "Lost", "Conversion rate (%)"]);

  // Other reports have no grouping; the campaign filter follows the tabs.
  await tab(page, "Counselor").click();
  await expect(page).toHaveURL(new RegExp(`report=counselor.*${filter}`));
  await expect(page.getByLabel("Group by")).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveText("No leads with a counselor in this range.");

  // Follow-up status: one open follow-up, not yet overdue.
  await tab(page, "Follow-up Status").click();
  await expect(page.getByRole("heading", { name: "Follow-up Status Report" })).toBeVisible();
  await expect(cells(page, `E2E N13 Telecaller ${stamp}`)).toHaveText(["1", "0", "1", "0", "0"]);

  // Pending: empty until the due time passes, then the follow-up is listed with its lead, reason and days overdue.
  await tab(page, "Pending Follow-ups").click();
  await expect(page.getByRole("status")).toHaveText("No overdue follow-ups in this range.");
  await expect.poll(async () => {
    await page.reload();
    return page.getByRole("table").getByRole("row", { name: new RegExp(`N13 Lead 1 ${stamp}`) }).count();
  }, { timeout: 120_000, intervals: [10_000] }).toBe(1);
  await expect(cells(page, new RegExp(`N13 Lead 1 ${stamp}`))).toHaveText([`E2E N13 Telecaller ${stamp}`, istToday(), "Need fee details", "0"]);

  // The CSV is the same list.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  const csv = readFileSync(await (await download).path(), "utf8");
  expect(csv.replace(/^﻿/, "").split(/\r?\n/)[0]).toBe("Lead,Telecaller,Due date,Reason,Days overdue");
  expect(csv).toContain(`N13 Lead 1 ${stamp},E2E N13 Telecaller ${stamp},${istToday()},Need fee details,0`);

  // The follow-up status now counts it overdue.
  await tab(page, "Follow-up Status").click();
  await expect(cells(page, `E2E N13 Telecaller ${stamp}`)).toHaveText(["1", "0", "1", "1", "0"]);

  // An unknown grouping is a message above the form.
  await page.goto(`${BASE}?report=date&group=year`);
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Choose day, week or month");

  for (const width of [820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const kind of ["date", "pending_follow_ups", "follow_ups"]) {
      await page.goto(`${BASE}?report=${kind}&${filter}`);
      expect(await noSideScroll(page), `${kind} at ${width}px`).toBe(true);
    }
  }
  expect(errors).toEqual([]);
});
