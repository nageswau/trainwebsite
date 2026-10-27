import { expect, test, type Page } from "@playwright/test";

// nehn-010 (DEC-SCOPE-305): the training reports pack in the report library. The IT admin finds all seven reports, filters the
// Attendance report to the seeded learner and downloads it; the Course-wise report's revenue column reaches the super admin only
// (field.financial); the seeded trainer's Trainer report holds only their own row; a wide report holds at phone width.

const PACK = [
  "Student-wise course report", "Students per trainer", "Course completion", "Completions in a period", "Attendance", "Trainer report",
  "Course-wise report",
];
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, loginPath: string, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test.describe("nehn-010 training reports", () => {
  test("IT admin finds the pack, filters Attendance to a learner and downloads it", async ({ page }) => {
    await signIn(page, "/it/login", "itadmin@edusphere.local");
    await page.goto("/it/admin/report-library");
    for (const title of PACK) await expect(page.locator("main").getByRole("link", { name: title, exact: true })).toBeVisible();

    await page.locator("main").getByRole("link", { name: "Attendance", exact: true }).click();
    await page.waitForURL("**report=attendance");
    await expect(page.locator("thead th")).toHaveText([
      "Student code", "Student", "Course", "Batch", "Trainer", "Classes marked", "Present", "Absent", "Late", "Excused", "Attendance %",
    ]);
    await page.getByText("Filters", { exact: true }).click();
    await page.fill("#report-student", "arjun rao");
    await page.getByRole("button", { name: "Apply" }).click();
    await page.waitForURL("**student=arjun**");
    await expect(page.locator("tbody td[data-label='Batch']")).toHaveText(["PY-FS-AUG-2026"]);

    const [excel] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download Excel" }).click()]);
    expect(excel.suggestedFilename()).toMatch(/^attendance-\d{4}-\d{2}-\d{2}\.xlsx$/);
  });

  test("the course-wise revenue column reaches the super admin only", async ({ page }) => {
    await signIn(page, "/it/login", "itadmin@edusphere.local");
    await page.goto("/it/admin/report-library?report=courses");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await expect(page.locator("thead th")).toHaveText(["Course", "Batches", "Enrolments", "Active", "Completed", "Dropped"]);

    await signIn(page, "/admin/login", "superadmin@edusphere.local");
    await page.goto("/admin/report-library?report=courses");
    await expect(page.locator("thead th").last()).toHaveText("Revenue (INR)");
  });

  test("a trainer's Trainer report holds only their own row", async ({ page }) => {
    await signIn(page, "/it/login", "trainer@edusphere.local");
    await page.goto("/it/trainer/report-library?report=trainers");
    await expect(page.locator("tbody th[scope=row]")).toHaveText(["Meera Iyer"]);
    await page.goto("/it/trainer/report-library?report=student-courses");
    expect(new Set(await page.locator("tbody td[data-label='Trainer']").allTextContents())).toEqual(new Set(["Meera Iyer"]));
  });

  test("a wide report holds at phone width", async ({ page }) => {
    await signIn(page, "/it/login", "itadmin@edusphere.local");
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/it/admin/report-library?report=student-courses");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
  });
});
