import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-009 (DEC-SCOPE-252) -- the counselor opens the seeded demo student's 360 from the Students section, walks the tabs (each one
// its own server read), saves the Preferences tab without losing the Academic tab's qualifications, and the Overseas Admin is kept in
// their own portal. The student is refused. Uses only seeded accounts (no account emails). Requires `python -m app.seed`.

const COUNSELOR = "counselor@edusphere.local";

test("a counselor works through a student's 360 and the admin stays in their portal (ccrm-009)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, COUNSELOR, "Demo@123", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/students");
  await page.getByRole("link", { name: /^Open / }).first().click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/students\/[0-9a-f-]{36}$/);
  const studentUrl = new URL(page.url()).pathname;
  const tabs = page.getByRole("navigation", { name: "Student record sections" });
  await expect(tabs.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Contact" })).toBeVisible();

  await tabs.getByRole("link", { name: /Applications/ }).click();
  await expect(page).toHaveURL(/tab=applications/);
  const overview = await (await page.request.get(studentUrl.replace("/overseas/counselor/students/", "/api/v1/counselor/students/") + "/overview")).json();
  for (const application of overview.applications) {
    await expect(page.getByText(application.university, { exact: true })).toBeVisible();
  }
  expect(overview.applications.filter((a: { mine: boolean }) => a.mine).length).toBeGreaterThan(0);

  for (const [name, text] of [["Documents", /Uploaded|No documents uploaded yet/], ["Activities", "Internal notes — the student and the agent never see them."], ["History", /Application|Nothing has been recorded yet/]] as const) {
    await tabs.getByRole("link", { name }).click();
    await expect(tabs.getByRole("link", { name })).toHaveAttribute("aria-current", "page");
    await expect(page.getByText(text).first()).toBeVisible();
  }

  await tabs.getByRole("link", { name: "Academic" }).click();
  await expect(page.getByText("Academic history")).toBeVisible();
  await expect(page.getByText("Study preferences")).toHaveCount(0);
  const qualifications = await page.getByText(/^Qualification \d+$/).count();

  await tabs.getByRole("link", { name: "Preferences" }).click();
  await expect(page.getByText("Academic history")).toHaveCount(0);
  const course = `MSc Analytics ${Date.now()}`;
  await page.getByLabel("Course or subject").fill(course);
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Profile saved.")).toBeVisible();
  await tabs.getByRole("link", { name: "Academic" }).click();
  await expect(page.getByText(/^Qualification \d+$/)).toHaveCount(qualifications);
  await tabs.getByRole("link", { name: "History" }).click();
  await expect(page.getByText("Profile updated: preferred course").first()).toBeVisible();

  expect((await page.request.get("/overseas/counselor/students/not-a-uuid")).status()).toBe(404);
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  expect((await page.request.get(`/api/v1/counselor/students/${overview.student.id}/overview`)).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`${studentUrl}?tab=history`);
  await expect(page).toHaveURL(`/overseas/admin/students/${overview.student.id}?tab=history`);
  await expect(page.getByText("Profile updated: preferred course").first()).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
