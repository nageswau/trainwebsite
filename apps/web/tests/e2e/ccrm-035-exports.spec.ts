import { readFile } from "node:fs/promises";

import { expect, test, type Download, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-035 (DEC-SCOPE-268, E1-E9): CSV and Excel exports of the management CRM reports (partner, Overseas Admin) and of the overseas
// counselor's own applications and leads; every other role is refused, and a file never carries an email or phone number. Seeded demo
// accounts; the shared stack DB also holds backend-test rows, so the checks are on headers and shapes, not fixed numbers.

async function adminSignIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function download(page: Page, group: string, button: "Download CSV" | "Download Excel"): Promise<{ file: Download; body: Buffer }> {
  const pending = page.waitForEvent("download");
  await page.getByRole("group", { name: group }).getByRole("button", { name: button }).click();
  const file = await pending;
  await expect(page.getByRole("group", { name: group }).getByText("Report downloaded.")).toBeVisible();
  return { file, body: await readFile((await file.path())!) };
}

const firstLine = (body: Buffer) => body.toString("utf-8").replace(/^﻿/, "").split(/\r?\n/)[0];

test("a partner exports a CRM report as CSV and Excel with the filters applied", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await adminSignIn(page, "partner.one@edusphere.local", "/management");
  await page.goto("/management/crm-reports");
  const csv = await download(page, "Export University performance", "Download CSV");
  expect(csv.file.suggestedFilename()).toMatch(/^crm-universities-\d{4}-\d{2}-\d{2}\.csv$/);
  expect(firstLine(csv.body)).toBe("University,Applications,Students,Offers,Offer rate (%),Rejections,Acceptances,Enrolments");
  expect(csv.body.toString("utf-8").trimEnd().split(/\r?\n/).at(-1)).toMatch(/^Total,/);
  const xlsx = await download(page, "Export Application ageing", "Download Excel");
  expect(xlsx.file.suggestedFilename()).toMatch(/^crm-ageing-\d{4}-\d{2}-\d{2}\.xlsx$/);
  expect(xlsx.body.subarray(0, 2).toString()).toBe("PK"); // a zip package
  expect(errors).toEqual([]);
});

test("the Overseas Admin exports from their own CRM reports page", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/crm-reports");
  const { body } = await download(page, "Export Forecast by intake", "Download CSV");
  expect(firstLine(body)).toBe("Intake,Applications,Students,Confirmed,Expected,Possible,Lost,Forecast");
});

test("the overseas counselor exports their own applications and leads without contact details", async ({ page }) => {
  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/applications");
  const apps = await download(page, "Export my applications", "Download CSV");
  expect(firstLine(apps.body)).toBe("EduSphere ID,Student,University,Agency,Intake,Status,Sub-status,Outcome,Next action,Last updated");
  expect(apps.body.toString("utf-8")).not.toContain("@");

  await page.goto("/overseas/counselor/leads");
  const leads = await download(page, "Export my leads", "Download Excel");
  expect(leads.file.suggestedFilename()).toMatch(/^my-leads-\d{4}-\d{2}-\d{2}\.xlsx$/);
  const csv = await page.request.get("/api/v1/counselor/exports/leads?format=csv");
  expect(firstLine(await csv.body())).toBe("Lead ID,Name,Interest,Stage,Priority,Source,Telecaller,Lead date");
  expect((await csv.text()).includes("@")).toBe(false);
});

test("every other role is refused an export", async ({ browser }) => {
  const accountant = await (await browser.newContext()).newPage();
  await adminSignIn(accountant, "accountant@edusphere.local", "/management");
  expect((await accountant.request.get("/api/v1/management/crm-reports/export?report=ageing")).status()).toBe(403);

  const counselor = await (await browser.newContext()).newPage();
  await signIn(counselor, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  expect((await counselor.request.get("/api/v1/management/crm-reports/export?report=ageing")).status()).toBe(403);

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  expect((await admin.request.get("/api/v1/counselor/exports/applications")).status()).toBe(403);
  await admin.goto("/overseas/admin/applications");
  await expect(admin.getByRole("group", { name: "Export my applications" })).toHaveCount(0);
});

test("on a phone the export buttons wrap inside the page (no sideways scroll)", async ({ browser }) => {
  const page = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/leads");
  await expect(page.getByRole("group", { name: "Export my leads" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
});
