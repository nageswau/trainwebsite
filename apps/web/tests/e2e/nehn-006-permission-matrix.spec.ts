import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// nehn-006 (DEC-SCOPE-295): the Super Admin's permission matrix, and the portals that follow it. Grants are role-wide, so every test
// that changes one restores the seed in `finally` (it_admin: nehn-005's DEFAULT_GRANTS).

const SUPER = { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" };
const IT_ADMIN = { email: "itadmin@edusphere.local", password: "Demo@123" };
const IT_ADMIN_SEED = ["certificates.configure", "discounts.add", "payments.add", "payments.view", "reports.telecaller.download", "reports.telecaller.view", "reports.training.download", "reports.training.view", "student_access.configure"]; // nehn-031 added certificates.configure; nehn-009 reports.training; nehn-018 student_access.configure
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function restoreItAdmin(request: APIRequestContext) {
  await request.post("/api/v1/auth/login", { data: SUPER });
  try {
    const response = await request.put("/api/v1/admin/roles/it_admin/permissions", { data: { permissions: IT_ADMIN_SEED } });
    expect(response.status(), await response.text()).toBe(200);
  } finally {
    await request.post("/api/v1/auth/logout");
  }
}

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function openMatrix(page: Page, roleLabel: string) {
  await page.goto("/admin");
  await page.locator(".portal-nav").getByRole("link", { name: "Permissions", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Permissions", exact: true })).toBeVisible();
  await page.getByLabel("Role", { exact: true }).selectOption({ label: roleLabel });
  await expect(page.getByRole("region", { name: `Permissions for ${roleLabel}` })).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("AC1: revoking it_admin's payments.view hides Payments and refuses the page; granting it back restores both", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const itPage = await admin.newPage();
  try {
    await signIn(page, "admin", SUPER.email, SUPER.password);
    await openMatrix(page, "IT Administrator");
    const view = page.getByRole("checkbox", { name: "Payments: View" });
    await expect(view).toBeChecked();
    await view.uncheck();
    await expect(page.getByText("1 unsaved change")).toBeVisible();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toHaveText("Saved IT Administrator: 1 change.");

    await signIn(itPage, "it", IT_ADMIN.email, IT_ADMIN.password);
    await itPage.goto("/it/admin/dashboard");
    const itNav = itPage.locator(".portal-nav");
    await expect(itNav.getByRole("link", { name: "Telecaller Reports" })).toBeVisible();
    await expect(itNav.getByRole("link", { name: "Payments", exact: true })).toHaveCount(0);
    await itPage.goto("/it/admin/payments");
    await expect(itPage.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(itPage.getByText("You do not have permission to view payments")).toBeVisible();

    // Grant it back through the screen; the IT admin's next page has Payments again.
    await page.reload();
    await page.getByLabel("Role", { exact: true }).selectOption({ label: "IT Administrator" });
    await page.getByRole("checkbox", { name: "Payments: View" }).check();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toHaveText("Saved IT Administrator: 1 change.");
    await itPage.goto("/it/admin/payments");
    await expect(itPage.getByRole("heading", { name: "Payments" }).first()).toBeVisible();
    await expect(itPage.locator(".portal-nav").getByRole("link", { name: "Payments", exact: true })).toBeVisible();
  } finally {
    await restoreItAdmin(admin.request);
    await admin.close();
  }
  expect(errors).toEqual([]);
});

test("AC6: without the download grant the report shows without its export; without discounts.add the discount form goes", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    await admin.request.post("/api/v1/auth/login", { data: SUPER });
    const response = await admin.request.put("/api/v1/admin/roles/it_admin/permissions", { data: { permissions: ["payments.add", "payments.view", "reports.telecaller.view"] } });
    expect(response.status()).toBe(200);
    await signIn(page, "it", IT_ADMIN.email, IT_ADMIN.password);
    await page.goto("/it/admin/telecaller-reports");
    await expect(page.getByRole("heading", { name: "Lead Source Report" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Download CSV" })).toHaveCount(0);
    await page.goto("/it/admin/payments");
    await expect(page.getByRole("heading", { name: "Create payment due" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Apply discount" })).toHaveCount(0);
  } finally {
    await restoreItAdmin(admin.request);
    await admin.close();
  }
  await page.goto("/it/admin/telecaller-reports");
  await expect(page.getByRole("button", { name: "Download CSV" })).toBeVisible();
});

test("AC2/AC4/AC7: the matrix is keyboard-operable, asks before leaving unsaved work, and fits a phone", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page, "admin", SUPER.email, SUPER.password);
  await openMatrix(page, "Coordinator");
  const table = page.getByRole("region", { name: "Permissions for Coordinator" });
  await expect(table.getByRole("columnheader")).toHaveCount(12); // the resource + rbac.ACTIONS (nehn-031 added override, configure)
  const certificates = page.getByRole("checkbox", { name: "Certificates: View" });
  await expect(certificates).toBeChecked();
  await certificates.focus();
  await page.keyboard.press("Space");
  await expect(certificates).not.toBeChecked();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByLabel("Role", { exact: true }).selectOption({ label: "IT Administrator" });
  await expect(page.getByLabel("Role", { exact: true })).toHaveValue("coordinator");
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(certificates).toBeChecked();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();

  await page.getByLabel("Role", { exact: true }).selectOption({ label: "Super Administrator" });
  await expect(page.getByText("always holds every permission")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Payments: View" })).toBeDisabled();

  for (const [width, height] of [[768, 1024], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.reload();
    await expect(page.getByRole("region", { name: /Permissions for/ })).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
  }
});

test("AC5: a non-super-admin opening /admin/permissions gets the access card", async ({ page }) => {
  await signIn(page, "it", IT_ADMIN.email, IT_ADMIN.password);
  await page.goto("/admin/permissions");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Only a super admin can manage permissions")).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
});
