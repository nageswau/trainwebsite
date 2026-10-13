import { expect, test, type Page } from "@playwright/test";

// mgmt-017 (spec TR1-TR16): the partner opens the Training dashboard from the Command Center, reads the §12 KPIs and the trainer table,
// and a chosen period survives a reload; the People "Trainers" entry opens the table; the super admin reaches it from their own sidebar;
// the accountant and a trainer are refused. The shared test database holds many rows, so the checks are about the page, not exact counts.

async function signIn(page: Page, email: string, loginPath = "/admin/login") {
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const kpis = (page: Page) => page.getByRole("list", { name: "Training KPIs" });
const table = (page: Page) => page.getByRole("table", { name: "Trainer performance" });

test("the partner reads the training KPIs and every trainer, and keeps a chosen period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Training", exact: true }).first().click();
  await expect(page).toHaveURL(/\/management\/training/);
  await expect(page.getByRole("heading", { name: "Training dashboard" })).toBeVisible();

  await expect(kpis(page).getByRole("listitem")).toHaveCount(11);
  await expect(table(page).getByRole("columnheader", { name: "Student feedback" })).toBeVisible();
  await expect(table(page).getByRole("rowheader", { name: "Meera Iyer" })).toBeVisible();
  await expect(page.getByText(/trainer accounts?/).first()).toBeVisible();

  await page.fill("#training-from", "2025-03-01");
  await page.fill("#training-to", "2025-03-31");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/from=2025-03-01&to=2025-03-31/);
  await page.reload();
  await expect(page.locator("#training-from")).toHaveValue("2025-03-01");

  await page.fill("#training-from", "2025-03-31");
  await page.fill("#training-to", "2025-03-01");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The period must start on or before its end");
});

test("an empty period says why a share is missing, never 0%", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/training?from=1900-06-01&to=1900-06-30");
  await expect(kpis(page).getByRole("listitem").filter({ hasText: "Attendance" })).toContainText("Nothing marked");
  await expect(kpis(page).getByRole("listitem").filter({ hasText: "Completion" })).toContainText("No seats taken");
});

test("the People Trainers entry opens the trainer table", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management");
  await page.getByRole("link", { name: "Trainers", exact: true }).first().click();
  await expect(page).toHaveURL(/\/management\/training#trainers/);
  await expect(table(page)).toBeVisible();
});

test("the super admin reaches the page from their own sidebar; the accountant and a trainer are refused", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local");
  await page.goto("/admin");
  await page.getByRole("link", { name: "Management training figures" }).first().click();
  await expect(page).toHaveURL(/\/management\/training/);
  await expect(kpis(page)).toBeVisible();

  for (const [email, loginPath] of [["accountant@edusphere.local", "/admin/login"], ["trainer@edusphere.local", "/it/login"]]) {
    await page.context().clearCookies();
    await signIn(page, email, loginPath);
    await page.goto("/management/training");
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(kpis(page)).toHaveCount(0);
  }
});

test("on a phone the page does not scroll sideways; the table scrolls in its own box", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "partner.one@edusphere.local");
  await page.goto("/management/training");
  await expect(table(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
