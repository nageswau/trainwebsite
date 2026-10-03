import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

import { E2E_PASSWORD } from "./helpers/welcome";
import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-020 (DEC-SCOPE-067) -- the agency Reports page: a Master's eight tabs and a CSV with the on-screen headers; staff with Reports
// see six tabs of their own students; staff without it get the server's refusal; the page fits a phone. Requires the stack running
// with `python -m app.seed` applied. Run in the browser-validation phase.

const MASTER_PASSWORD = "Sup3r-Secret-Pass!";
const STAFF = "/api/v1/workflows/overseas/agent/team/staff";

test("Masters get every report and a CSV; staff get their own reports or the refusal (AGN-020)", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn020");
  const api = page.request;
  await api.post("/api/v1/auth/login", { data: { email: masterEmail, password: MASTER_PASSWORD, division: "overseas" } });
  const student = `Zoë AGN020 ${unique}`;
  expect((await api.post("/api/v1/workflows/overseas/agent/crm/students", { data: { full_name: student } })).ok()).toBeTruthy();
  const withReports = `agn020-on-${unique}@example.local`;
  const withoutReports = `agn020-off-${unique}@example.local`;
  const created = await api.post(STAFF, { data: { full_name: "AGN020 Reports On", email: withReports } });
  const memberId = ((await created.json()) as { member: { id: string } }).member.id;
  expect((await api.put(`${STAFF}/${memberId}/permissions`, { data: { can_view_reports: true, can_verify_documents: false } })).ok()).toBeTruthy();
  expect((await api.post(STAFF, { data: { full_name: "AGN020 Reports Off", email: withoutReports } })).ok()).toBeTruthy();

  // Master: eight tabs, the Students report, its CSV with the on-screen header row.
  await signIn(page, masterEmail, MASTER_PASSWORD);
  await page.goto("/overseas/agent/reports");
  const tabs = page.getByRole("tablist", { name: "Reports" }).getByRole("tab");
  await expect(tabs).toHaveCount(8);
  await expect(page.getByRole("region", { name: "Students" })).toContainText(student);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("agency-students-all-to-all.csv");
  const csv = await readFile((await file.path()) as string, "utf8");
  expect(csv.replace(/^﻿/, "").split(/\r?\n/)[0]).toBe("Name,Assigned staff,Preferred country,Preferred intake,Status,Created,Applications");
  expect(csv).toContain(student);

  // Keyboard: the arrow keys move along the tabs and open the report; the address keeps it.
  await page.getByRole("tab", { name: "Students" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Applications" })).toHaveAttribute("aria-selected", "true");
  await expect.poll(() => new URL(page.url()).searchParams.get("report")).toBe("applications");
  await page.getByRole("tab", { name: "Commission" }).click();
  await expect(page.getByRole("heading", { name: "Commission report" })).toBeVisible();

  // Staff with Reports: six tabs, no Staff performance or Commission.
  const on = await (await browser.newContext()).newPage();
  await adminActivate(on.request, withReports);
  await signIn(on, withReports, E2E_PASSWORD);
  await on.goto("/overseas/agent/reports");
  await expect(on.getByRole("tablist", { name: "Reports" }).getByRole("tab")).toHaveCount(6);
  await expect(on.getByRole("tab", { name: "Staff performance" })).toHaveCount(0);
  await expect(on.getByRole("tab", { name: "Commission" })).toHaveCount(0);

  // Staff without Reports: the server's refusal on a typed URL.
  const off = await (await browser.newContext()).newPage();
  await adminActivate(off.request, withoutReports);
  await signIn(off, withoutReports, E2E_PASSWORD);
  await off.goto("/overseas/agent/reports");
  await expect(off.getByText("Your agency Master hasn't given you access to reports")).toBeVisible();
});

test("the Reports page fits a 375 px phone (AGN-020)", async ({ page }) => {
  const masterEmail = await registerApprovedAgency(page, Date.now(), "agn020p");
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, masterEmail, MASTER_PASSWORD);
  await page.goto("/overseas/agent/reports?report=countries");
  await expect(page.getByRole("heading", { name: "Applications by country" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
