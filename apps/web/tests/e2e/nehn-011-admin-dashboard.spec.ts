import { expect, test, type Page } from "@playwright/test";

// nehn-011 (DEC-SCOPE-311): the admin dashboard's training tiles. The Super Admin sees them (fees included) and the at-risk tile
// opens the attendance report filtered at the threshold, whose row count is the tile's value; the IT Admin sees the tiles without the
// fee figures (no financial grant by default); the Overseas Admin sees none. The tiles hold at tablet and phone widths.

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const tile = (page: Page, label: string) => page.locator(".training-tiles a.metric", { hasText: label });

async function signIn(page: Page, loginPath: string, email: string) {
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test.describe("nehn-011 admin dashboard tiles", () => {
  test("Super Admin: the at-risk tile opens the attendance report pre-filtered, with as many rows as the tile says", async ({ page }) => {
    await signIn(page, "/admin/login", "superadmin@edusphere.local");
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Training overview" })).toBeVisible();
    for (const label of ["Enrolments", "Active", "Completed", "Dropped", "Average progress", "At-risk students", "Course fees collected", "Course fees pending"]) {
      await expect(tile(page, label)).toBeVisible();
    }
    await expect(page.getByRole("table", { name: "Course-wise summary" })).toBeVisible();
    const atRisk = Number(await tile(page, "At-risk students").locator("strong").textContent());
    await tile(page, "At-risk students").click();
    await page.waitForURL("**/admin/report-library?report=attendance&attendance_below=*");
    await expect(page.getByRole("heading", { name: "Attendance" })).toBeVisible();
    await expect(page.getByLabel("Attendance below %")).toHaveValue(/^\d+$/);
    if (atRisk === 0) await expect(page.getByText("No rows match these filters.")).toBeVisible();
    else await expect(page.locator(".pager .muted")).toContainText(`of ${atRisk}`);
  });

  test("IT Admin sees the tiles without fee figures; they link into the IT report library", async ({ page }) => {
    await signIn(page, "/it/login", "itadmin@edusphere.local");
    await page.goto("/it/admin/dashboard");
    await expect(page.getByRole("heading", { name: "Training overview" })).toBeVisible();
    await expect(tile(page, "Course fees collected")).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "Revenue (INR)" })).toHaveCount(0);
    await tile(page, "Completed").click();
    await page.waitForURL("**/it/admin/report-library?report=completions");
    await expect(page.getByRole("heading", { name: "Completions in a period" })).toBeVisible();
  });

  test("Overseas Admin's dashboard has no training tiles", async ({ page }) => {
    await signIn(page, "/overseas/login", "overseasadmin@edusphere.local");
    await page.goto("/overseas/admin/dashboard");
    await expect(page.getByRole("heading", { name: "Administration Dashboard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Training overview" })).toHaveCount(0);
  });

  for (const [name, width] of [["tablet", 820], ["phone", 375]] as const) {
    test(`the tiles fit a ${name}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, "/it/login", "itadmin@edusphere.local");
      await page.goto("/it/admin/dashboard");
      await expect(page.getByRole("heading", { name: "Training overview" })).toBeVisible();
      expect(await noSideScroll(page)).toBe(true);
    });
  }
});
