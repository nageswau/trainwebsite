import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-031 (§32 "Reports"; spec RP1-RP14): a manager opens Reports from the sidebar, the pipeline total matches the dashboard, the expected
// report filters by window (and Back shows the window of the address, QA31-01), a refused filter is explained, the CSV downloads with the
// on-screen header; the head reads the team's targets; a counselor is refused; the page fits a phone. Throwaway accounts via the admin API.

const istToday = () => new Date(Date.now() + 330 * 60_000).toISOString().slice(0, 10);

async function signIn(page: Page, loginPath: string, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function send(page: Page, method: "post" | "patch", url: string, data: unknown) {
  const response = await page.request[method](url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123", "/admin");
  const head = await send(page, "post", "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc031-h-${stamp}@example.local` });
  const manager = await send(page, "post", "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc031-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U31-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const university = async (name: string) => {
    const { university: made } = await send(page, "post", "/api/v1/partnership/universities", { name: `${name} ${stamp}`, country_id: countries.items[0].id, city: "London" });
    await send(page, "post", `/api/v1/partnership/universities/${made.id}/assign`, { primary_manager_user_id: manager.id });
    return made;
  };
  const engaged = await university("E2E Reports Engaged");
  await send(page, "post", `/api/v1/partnership/universities/${engaged.id}/stage`, { to_stage: "interested", from_stage: "target_university" });
  await send(page, "patch", `/api/v1/partnership/universities/${engaged.id}/expected`, { expected_agreement_date: istToday() }); // 40%
  await university("E2E Reports Undated");
  const counselor = await send(page, "post", "/api/v1/admin/users", { role: "counselor", division: "overseas", full_name: `E2E Counselor ${stamp}`, email: `upc031-c-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager, counselor]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, counselor };
}

const tab = (page: Page, name: string) => page.getByRole("navigation", { name: "Reports" }).getByRole("link", { name });

test("a manager reads and downloads their reports; the head reads the team's; a counselor is refused", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, manager, counselor } = await setUp(page, stamp);

  await signIn(page, "/overseas/login", manager.email, E2E_PASSWORD, "/partnership/dashboard");
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Pipeline by Country Report" })).toBeVisible();
  // RP5 / AC: the Total row equals the dashboard's Total Universities.
  const table = page.getByRole("table");
  await expect(table.locator("tfoot").getByRole("rowheader")).toHaveText("Total");
  await expect(table.locator("tfoot td").first()).toHaveText("2");

  // RP6: the expected report by window; Back shows the address's window (QA31-01).
  await tab(page, "Expected Partnerships").click();
  await expect(tab(page, "Expected Partnerships")).toHaveAttribute("aria-current", "page");
  await expect(table.getByRole("rowheader", { name: `E2E Reports Engaged ${stamp}` })).toBeVisible();
  await expect(table.locator("tfoot td").last()).toHaveText("0.4");
  await page.getByLabel("Expected date window").selectOption("undated");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL("**window=undated**");
  await expect(table.getByRole("rowheader", { name: `E2E Reports Undated ${stamp}` })).toBeVisible();
  await page.reload();
  await page.goBack();
  await page.waitForURL((url) => !url.search.includes("window="));
  await expect(page.getByLabel("Expected date window")).toHaveValue("all");
  await expect(table.getByRole("rowheader", { name: `E2E Reports Engaged ${stamp}` })).toBeVisible();

  // RP10: a refused filter is explained above the form.
  await page.goto("/partnership/reports?report=performance&from=2026-10-10&to=2026-10-01");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");

  // RP13: the CSV has the on-screen header and the Total row.
  await page.goto("/partnership/reports?report=expected");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^partnership-expected-\d{4}-\d{2}-\d{2}\.csv$/);
  const csv = readFileSync((await download.path())!, "utf8");
  expect(csv.startsWith("﻿University,Code,Country,Stage,Expected date,Owner,Probability (%),Weighted")).toBe(true);
  expect(csv.trim().split(/\r?\n/).at(-1)).toMatch(/^Total,/);
  await expect(page.getByText("Report downloaded.")).toBeVisible();

  // A phone: the table stacks, nothing scrolls sideways.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/partnership/reports?report=targets");
  await expect(page.getByRole("table")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1280, height: 800 });

  // RP9: the head reads the team's targets (their manager is a row).
  await signIn(page, "/admin/login", head.email, E2E_PASSWORD, "/partnership/head/team");
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await tab(page, "Targets vs Actual").click();
  await expect(page.getByRole("table").getByRole("rowheader", { name: `E2E Manager ${stamp}` })).toBeVisible();

  // RP2: a counselor is refused.
  await signIn(page, "/overseas/login", counselor.email, E2E_PASSWORD, "/overseas/counselor**");
  await page.goto("/partnership/reports");
  await expect(page.getByText("Partnership reports access required")).toBeVisible();
  expect((await page.request.get("/api/v1/partnership/reports/pipeline.csv")).status()).toBe(403);
});
