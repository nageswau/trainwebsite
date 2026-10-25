import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-039 (DEC-SCOPE-272) -- the counselor opens the seeded demo student's 360 Finance tab: read-only fees (the seed's paid service
// fee), deposits and refunds, each section empty in words when there is nothing; no invoice/receipt download for the counselor. The
// Overseas Admin is kept in their own portal; the student is refused. Uses only seeded accounts. Requires `python -m app.seed`.

test("a counselor reads a student's finance tab; the admin stays in their portal; the student is refused (ccrm-039)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/students");
  await page.getByRole("link", { name: /^Open / }).first().click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/students\/[0-9a-f-]{36}$/);
  const studentUrl = new URL(page.url()).pathname;
  const tabs = page.getByRole("navigation", { name: "Student record sections" });
  await tabs.getByRole("link", { name: "Finance" }).click();
  await expect(page).toHaveURL(/tab=finance/);
  await expect(tabs.getByRole("link", { name: "Finance" })).toHaveAttribute("aria-current", "page");

  const finance = await (await page.request.get(studentUrl.replace("/overseas/counselor/students/", "/api/v1/counselor/students/") + "/finance")).json();
  const fees = page.getByRole("region", { name: "Fees and payments" });
  await expect(fees).toBeVisible();
  if (finance.payments.length === 0) await expect(fees.getByText("No fees or payments recorded for this student.")).toBeVisible();
  else await expect(fees.getByText(finance.payments[0].description).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "University deposits" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Refunds" })).toBeVisible();
  await expect(fees.getByRole("button", { name: /Download (invoice|receipt)/ })).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("region", { name: "Fees and payments" })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  const studentId = studentUrl.split("/").pop();
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  expect((await page.request.get(`/api/v1/counselor/students/${studentId}/finance`)).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`${studentUrl}?tab=finance`);
  await expect(page).toHaveURL(`/overseas/admin/students/${studentId}?tab=finance`);
  await expect(page.getByRole("region", { name: "Fees and payments" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
