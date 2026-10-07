import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-024 (DEC-SCOPE-109): a manager's campaign with three leads, one of them reached by a connected call. The manager reads the
// Campaign, Lead Source and Telecaller reports (filters kept across the report links), downloads the CSV, sees a refused range as a
// message, and the page holds at tablet and phone widths. A telecaller is refused; the IT admin reads their division's figures.

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const BASE = "/telecaller/manager/reports";

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Rep Manager ${stamp}`, email: `tel024-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Rep Telecaller ${stamp}`, email: `tel024-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `RP-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const product = await (await page.request.post("/api/v1/telecaller/products", { data: { group: "it", name: `E2E Course ${stamp}` } })).json();
  const campaign = await (await page.request.post("/api/v1/telecaller/campaigns", {
    data: { name: `E2E Campaign ${stamp}`, source: "instagram", product_id: product.id, start_date: "2026-01-01" },
  })).json();
  expect(campaign.id).toBeTruthy();
  const leads: string[] = [];
  for (const i of [0, 1, 2]) {
    const created = await page.request.post("/api/v1/telecaller/leads", {
      data: { name: `Rep Lead ${i} ${stamp}`, phone: `9${String(stamp).slice(-8)}${i}`, product_id: product.id, campaign_id: campaign.id, source: "instagram", division: "it" },
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

async function signIn(page: Page, portal: "it" | "admin", email: string, password = E2E_PASSWORD) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const cells = (page: Page, name: string | RegExp) => page.getByRole("table").getByRole("row", { name }).getByRole("cell");

test("a manager reads, filters and exports the telecaller reports; a telecaller is refused", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const { manager, caller, campaign, leads } = await setup(page, stamp);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));

  // The telecaller reaches one lead (a connected call moves it to Contacted), then is refused the reports.
  await signIn(page, "it", caller.email);
  const call = await page.request.post(`/api/v1/telecaller/leads/${leads[0]}/calls`, { data: { duration_seconds: 60, call_type: "outgoing", outcome: "interested" } });
  expect(call.status(), await call.text()).toBe(201);
  expect((await page.request.get("/api/v1/telecaller/reports/campaign")).status()).toBe(403);
  await page.goto(BASE);
  await expect(page.getByText("Telecaller manager role required")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "admin", manager.email);
  await page.getByRole("link", { name: "Reports", exact: true }).first().click();
  await page.waitForURL(`**${BASE}`);
  await expect(page.getByRole("heading", { name: "Lead Source Report" })).toBeVisible();

  // Campaign report for this campaign: 3 leads; the "interested" call moved one lead to Interested, past Qualified, so it counts as
  // Connected and Qualified (cumulative rule). Total row.
  await page.goto(`${BASE}?report=campaign&campaign_id=${campaign.id}`);
  await expect(page.getByRole("navigation", { name: "Reports" }).getByRole("link", { name: "Campaign" })).toHaveAttribute("aria-current", "page");
  await expect(cells(page, new RegExp(`E2E Campaign ${stamp}`))).toHaveText(["3", "1", "1", "0", "0"]);
  await expect(cells(page, /^Total/)).toHaveText(["3", "1", "1", "0", "0"]);

  // The CSV is the same table.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  const csv = readFileSync(await (await download).path(), "utf8");
  expect(csv.replace(/^﻿/, "").split(/\r?\n/)[0]).toBe("Campaign,Leads,Connected,Qualified,Counselling,Enrolled");
  expect(csv).toContain(`E2E Campaign ${stamp},3,1,1,0,0`);
  await expect(page.getByText("Report downloaded.")).toBeVisible();

  // The Lead Source link keeps the campaign filter.
  await page.getByRole("link", { name: "Lead Source" }).click();
  await expect(page).toHaveURL(new RegExp(`report=source.*campaign_id=${campaign.id}`));
  await expect(cells(page, /^Instagram/)).toHaveText(["3", "1", "1", "0", "0"]);

  // The Telecaller report counts activity (D11: only explicit moves to Qualified): the call is the telecaller's; no lead filters.
  await page.getByRole("link", { name: "Telecaller", exact: true }).click();
  await expect(page.getByLabel("Course")).toHaveCount(0);
  await expect(cells(page, `E2E Rep Telecaller ${stamp}`)).toHaveText(["1", "1", "0", "0", "0"]);

  // A reversed range is a message above the form, which keeps the typed dates.
  await page.goto(`${BASE}?report=source&date_from=2026-10-09&date_to=2026-10-01`);
  await expect(page.locator(".form-error[role=alert]")).toHaveText("'From' must be on or before 'To'"); // not Next's route announcer
  await expect(page.getByLabel("From")).toHaveValue("2026-10-09");

  // Filtering through the form: a source with no leads in this campaign is the empty state.
  await page.goto(`${BASE}?report=campaign&campaign_id=${campaign.id}`);
  await page.getByLabel("Source").selectOption("google");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("status")).toHaveText("No leads in this range.");
  await page.getByRole("link", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(new RegExp(`${BASE}\\?report=campaign$`));

  for (const width of [820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${BASE}?report=handover`);
    expect(await noSideScroll(page)).toBe(true);
  }
  expect(errors).toEqual([]);
});

test("a division admin reads the reports for their own division", async ({ page }) => {
  await signIn(page, "it", "itadmin@edusphere.local", "Demo@123");
  await page.goto("/it/admin/telecaller-reports?report=source");
  await expect(page.getByRole("heading", { name: "Lead Source Report" })).toBeVisible();
  await expect(page.getByLabel("Team")).toHaveCount(0); // one division: nothing to choose
  await expect(page.getByRole("link", { name: "Telecaller Reports" }).first()).toBeVisible();
  const body = await (await page.request.get("/api/v1/telecaller/reports/source?team=overseas")).json();
  expect(body.items).toEqual([]);
});
