import { expect, test, type Page } from "@playwright/test";

// mgmt-016 (spec SF1-SF16): the partner opens the Student funnel from the Command Center, reads the three paths, breaks them down and
// keeps the choice over a reload; Branch says it is not tracked; the super admin reaches it from their own sidebar; the accountant and a
// counselor are refused. The shared test database holds many rows, so the checks are about the page and its sums, not exact counts.

async function signIn(page: Page, email: string, loginPath = "/admin/login") {
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const path = (page: Page, name: string) => page.getByRole("list", { name });
const count = (page: Page, pathName: string, stage: string) =>
  path(page, pathName).getByRole("listitem").filter({ has: page.locator(".pipeline-label", { hasText: new RegExp(`^${stage}$`) }) }).locator(".pipeline-count").innerText();

test("the partner reads the funnel, breaks it down by counselor, and keeps the choice", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Student funnel", exact: true }).first().click();
  await expect(page).toHaveURL(/\/management\/funnel/);
  await expect(page.getByRole("heading", { name: "Student funnel" })).toBeVisible();
  await expect(path(page, "Lead journey").getByRole("listitem")).toHaveCount(4);
  await expect(path(page, "IT training").getByRole("listitem")).toHaveCount(5);
  await expect(path(page, "Abroad education").getByRole("listitem")).toHaveCount(5);

  await page.fill("#funnel-from", "2026-10-01");
  await page.fill("#funnel-to", "2026-10-31");
  await page.selectOption("#funnel-by", "counselor");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/from=2026-10-01&to=2026-10-31&by=counselor/);
  await page.reload();
  await expect(page.locator("#funnel-by")).toHaveValue("counselor");

  // AC2: the Total row is the stage's own count.
  const table = page.getByRole("table", { name: "Student funnel by Counselor" });
  await expect(table.locator("tfoot td").first()).toHaveText(await count(page, "Lead journey", "Leads"));
  await expect(table.getByRole("rowheader", { name: "Unknown" })).toBeVisible();
  await expect(page.getByText(/Not broken down by Counselor: Training/)).toBeVisible();
});

test("Branch is not tracked, and a reversed period shows the API's message", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/funnel?by=branch");
  await expect(page.locator("p[role=status]")).toHaveText(/Branch is not tracked in EduSphere yet/);
  await expect(page.getByRole("table")).toHaveCount(0);
  await page.goto("/management/funnel?from=2025-03-31&to=2025-03-01");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("the super admin reaches the page from their own sidebar; the accountant and a counselor are refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management student funnel" }).first().click();
  await expect(page).toHaveURL(/\/management\/funnel/);
  await expect(path(page, "Lead journey")).toBeVisible();

  for (const [email, loginPath] of [["accountant@edusphere.local", "/admin/login"], ["counselor@edusphere.local", "/overseas/login"]]) {
    await page.context().clearCookies();
    await signIn(page, email, loginPath);
    await page.goto("/management/funnel");
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(path(page, "Lead journey")).toHaveCount(0);
  }
});

test("on a phone the paths stack and the page does not scroll sideways; the table scrolls in its own box", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/funnel?by=counselor");
  await expect(page.getByRole("table")).toBeVisible();
  const [it, abroad] = await Promise.all([path(page, "IT training").boundingBox(), path(page, "Abroad education").boundingBox()]);
  expect(abroad!.y).toBeGreaterThan(it!.y + it!.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
