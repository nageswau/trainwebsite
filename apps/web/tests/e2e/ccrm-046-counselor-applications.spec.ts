import { test, expect, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ccrm-046 (DEC-SCOPE-324) -- the counselor adds two applications for a walk-in student from the 360's Applications tab, a duplicate is
// refused in the form, a student outside the caseload is refused by the API, and the student sees both applications in their portal.
// Requires the stack running with `python -m app.seed` applied; the spec makes its own counselors and students.

async function noSideScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

test("a counselor creates several applications for a walk-in student from the 360 (ccrm-046)", async ({ page, request }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const year = String(new Date().getFullYear() + 1);
  const counselorEmail = `ccrm046-cns-${unique}@example.local`;
  const studentEmail = `ccrm046-s-${unique}@example.local`;

  expect((await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } })).ok()).toBeTruthy();
  const counselor = await createAndActivate(request, "/api/v1/admin/users", { email: counselorEmail, full_name: "Apply Counselor", role: "counselor", division: "overseas" });
  const student = await createAndActivate(request, "/api/v1/admin/users", { email: studentEmail, full_name: `Apply Student ${unique}`, role: "overseas_student", division: "overseas" });
  const stranger = await createAndActivate(request, "/api/v1/admin/users", { email: `ccrm046-x-${unique}@example.local`, full_name: `Stranger ${unique}`, role: "overseas_student", division: "overseas" });
  expect((await request.put(`/api/v1/admin/users/${student.id}/counselor`, { data: { counselor_id: counselor.id } })).ok()).toBeTruthy();
  // names must be unique: backend tests on the same stack DB leave several universities with one name
  const all = (await (await request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const universities = all.filter((u) => all.filter((v) => v.name === u.name).length === 1);

  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  await page.goto(`/overseas/counselor/students/${student.id}?tab=applications`);
  await expect(page.getByText("This student has no applications yet.")).toBeVisible();
  await page.getByText("Add application", { exact: true }).click();

  async function apply(universityId: string) {
    await page.getByLabel("University").selectOption(universityId);
    await page.getByLabel("Intake month").selectOption("Sep");
    await page.getByLabel("Intake year").selectOption(year);
    await page.getByRole("button", { name: "Create application" }).click();
  }

  // Two universities, one after the other, without leaving the tab (AC1); the list and the tab count follow.
  for (const [n, uni] of universities.slice(0, 2).entries()) {
    await apply(uni.id);
    await expect(page.getByText("Application created. It is listed below.")).toBeVisible();
    await expect(page.locator(".s360-list > li")).toHaveCount(n + 1);
    await expect(page.locator(".s360-list > li", { hasText: uni.name }).getByText(/APP-\d{6}/)).toBeVisible(); // AC2
  }
  await expect(page.locator(".s360-list > li .badge", { hasText: "Yours" })).toHaveCount(2);
  await expect(page.getByRole("link", { name: /Applications/ }).locator(".s360-count")).toHaveText("2");

  // The same university again while open is refused (AC3).
  await apply(universities[0].id);
  await expect(page.locator(".form-error", { hasText: "This student already has an open application for this university and course." })).toBeVisible();
  await expect(page.locator(".s360-list > li")).toHaveCount(2);

  // A student outside the caseload: no 360, and the API refuses (AC4).
  const refused = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: stranger.id, university_id: universities[0].id, intake: `Sep ${year}` } });
  expect(refused.status()).toBe(403);

  for (const width of [768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/overseas/counselor/students/${student.id}?tab=applications`);
    await page.getByText("Add application", { exact: true }).click();
    await expect(page.getByRole("button", { name: "Create application" })).toBeVisible();
    await noSideScroll(page);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // The student sees both in their portal (AC6).
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, studentEmail, E2E_PASSWORD, "/overseas/student/dashboard");
  const rows = (await (await page.request.get("/api/v1/portal/overseas/student/applications")).json()).rows as { university: string }[];
  expect(rows.map((r) => r.university).sort()).toEqual(universities.slice(0, 2).map((u) => u.name).sort());

  expect(consoleErrors.filter((e) => !e.includes("status of 409"))).toEqual([]); // the 409 is the refused duplicate above
});
