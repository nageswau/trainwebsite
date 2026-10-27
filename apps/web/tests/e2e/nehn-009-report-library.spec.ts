import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

// nehn-009 (DEC-SCOPE-303): the report library. The IT admin opens it from the sidebar, opens the Enrollments report, filters it (the
// filters fold away until one is applied), downloads the filtered rows as Excel and CSV, sees a refused range as a message above the
// kept form and a page past the end as such; the page holds at tablet and phone widths. The seeded trainer sees only their own batch;
// a student is refused on the page and the API.

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const ADMIN = "/it/admin/report-library";

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test.describe("nehn-009 report library", () => {
  test("IT admin filters the Enrollments report and downloads the matching rows", async ({ page }) => {
    await signIn(page, "itadmin@edusphere.local");
    await page.goto("/it/admin/dashboard");
    await page.getByRole("link", { name: "Report library" }).click();
    await page.waitForURL(`**${ADMIN}`);
    await page.locator("main").getByRole("link", { name: "Enrollments" }).click();
    await page.waitForURL("**report=enrollments");
    await expect(page.getByRole("heading", { name: "Enrollments" })).toBeVisible();
    await expect(page.locator(".pager .muted")).toContainText("Showing 1–");

    await page.getByText("Filters", { exact: true }).click();
    await page.selectOption("#report-status", "active");
    await page.fill("#report-student", "arjun rao");
    await page.fill("#report-latest", "1");
    await page.getByRole("button", { name: "Apply" }).click();
    await page.waitForURL("**latest=1**");
    await expect(page.locator("details.map-filters > summary")).toHaveText("Filters (3 applied)");
    await expect(page.locator("tbody tr")).toHaveCount(1);
    await expect(page.locator("tbody th[scope=row]")).toHaveText("EDU-202608-0001");

    const [excel] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download Excel" }).click()]);
    expect(excel.suggestedFilename()).toMatch(/^enrollments-\d{4}-\d{2}-\d{2}\.xlsx$/);
    const [csv] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
    const lines = readFileSync(await csv.path()).toString("utf8").replace(/^﻿/, "").trim().split(/\r?\n/);
    expect(lines[0]).toBe("Enrollment code,Student code,Student,Course,Batch,Trainer,Enrolled on,Batch ends,Status,Progress %");
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain("EDU-202608-0001");
  });

  test("a refused range keeps the form, and a page past the end says so", async ({ page }) => {
    await signIn(page, "itadmin@edusphere.local");
    await page.goto(`${ADMIN}?report=enrollments&from=2026-10-10&to=2026-10-01`);
    await expect(page.locator(".form-error")).toHaveText("'From' must be on or before 'To'");
    await expect(page.locator("#report-from")).toHaveValue("2026-10-10");
    await page.goto(`${ADMIN}?report=enrollments&page=999`);
    await expect(page.getByRole("status").filter({ hasText: "past the last row" })).toBeVisible();
    await page.getByRole("link", { name: "Go to the first page" }).click();
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await page.goto(`${ADMIN}?report=nothing`);
    await expect(page.locator(".form-error")).toHaveText("That report isn't available to you.");
  });

  test("the report holds at tablet and phone widths", async ({ page }) => {
    await signIn(page, "itadmin@edusphere.local");
    for (const viewport of [{ width: 768, height: 1024 }, { width: 375, height: 800 }]) {
      await page.setViewportSize(viewport);
      await page.goto(`${ADMIN}?report=enrollments`);
      await expect(page.locator("tbody tr").first()).toBeVisible();
      expect(await noSideScroll(page)).toBe(true);
    }
  });

  test("a trainer sees only their own batch; a student is refused", async ({ page, browser }) => {
    await signIn(page, "trainer@edusphere.local");
    await page.goto("/it/trainer/dashboard");
    await page.getByRole("link", { name: "Report library" }).click();
    await page.waitForURL("**/it/trainer/report-library");
    await page.goto("/it/trainer/report-library?report=enrollments");
    const batches = new Set(await page.locator("tbody td[data-label='Batch']").allTextContents());
    expect([...batches]).toEqual(["PY-FS-AUG-2026"]);
    await expect(page.locator("#report-trainer_id option")).toHaveText(["All trainers", "Meera Iyer"]);

    const student = await browser.newPage();
    await signIn(student, "student.it@edusphere.local");
    await student.goto("/it/trainer/report-library");
    await expect(student.getByText("Trainer role required")).toBeVisible();
    const api = await student.request.get("/api/v1/reports/enrollments");
    expect(api.status()).toBe(403);
    await student.close();
  });
});
