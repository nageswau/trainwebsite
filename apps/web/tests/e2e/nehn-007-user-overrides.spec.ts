import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// nehn-007 (DEC-SCOPE-298): per-user permission overrides on the Permissions screen's "By user" tab. Every test that sets an override
// on the seeded IT admin clears that user's overrides in `finally`.

const SUPER = { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" };
const IT_ADMIN = { email: "itadmin@edusphere.local", password: "Demo@123" };
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function asSuper<T>(request: APIRequestContext, work: () => Promise<T>): Promise<T> {
  await request.post("/api/v1/auth/login", { data: SUPER });
  try {
    return await work();
  } finally {
    await request.post("/api/v1/auth/logout");
  }
}

async function itAdminId(request: APIRequestContext): Promise<string> {
  return asSuper(request, async () => {
    const users = (await (await request.get(`/api/v1/admin/users?q=${encodeURIComponent(IT_ADMIN.email)}`)).json()) as { id: string; email: string }[];
    return users.find((u) => u.email === IT_ADMIN.email)!.id;
  });
}

async function clearOverrides(request: APIRequestContext, id: string) {
  await asSuper(request, async () => {
    const response = await request.put(`/api/v1/admin/users/${id}/permissions`, { data: { overrides: [] } });
    expect(response.status(), await response.text()).toBe(200);
  });
}

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test.describe.configure({ mode: "serial" });

test("AC1/AC5: a deny on one IT admin hides Payments for that user, is listed, and clearing it restores access", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const other = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const itPage = await other.newPage();
  const id = await itAdminId(other.request);
  try {
    await signIn(page, "admin", SUPER.email, SUPER.password);
    await page.goto("/admin/permissions");
    await page.getByRole("link", { name: "By user" }).click();
    await expect(page).toHaveURL(/tab=user/);
    await page.getByLabel("Find a user").fill(IT_ADMIN.email);
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByRole("list", { name: "Matching users" }).getByRole("link").first().click();
    await expect(page).toHaveURL(new RegExp(`user=${id}`));
    const view = page.getByRole("combobox", { name: "Payments: View override" });
    await expect(view).toHaveValue("");
    await view.selectOption("deny");
    await page.getByLabel("Payments: View reason").fill("E2E: payments freeze");
    await page.getByRole("button", { name: "Save overrides" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved overrides" })).toBeVisible();
    await expect(page.getByRole("row", { name: /^Payments: View/ }).getByText("Denied by override")).toBeVisible();
    const report = page.getByRole("table", { name: "Active overrides" });
    await expect(report.getByRole("row", { name: /E2E: payments freeze/ })).toBeVisible();

    // Refresh keeps the tab and the user.
    await page.reload();
    await expect(page.getByRole("combobox", { name: "Payments: View override" })).toHaveValue("deny");

    await signIn(itPage, "it", IT_ADMIN.email, IT_ADMIN.password);
    await itPage.goto("/it/admin/dashboard");
    await expect(itPage.locator(".portal-nav").getByRole("link", { name: "Payments", exact: true })).toHaveCount(0);
    await itPage.goto("/it/admin/payments");
    await expect(itPage.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

    // Clear it through the screen; the IT admin's next page has Payments again.
    await page.getByRole("combobox", { name: "Payments: View override" }).selectOption("");
    await page.getByRole("button", { name: "Save overrides" }).click();
    await expect(page.getByText("No user has an override.").or(report.getByRole("row", { name: /E2E: payments freeze/ })).first()).toBeVisible();
    await expect(report.getByRole("row", { name: /E2E: payments freeze/ })).toHaveCount(0);
    await itPage.goto("/it/admin/payments");
    await expect(itPage.locator(".portal-nav").getByRole("link", { name: "Payments", exact: true })).toBeVisible();
  } finally {
    await clearOverrides(other.request, id);
    await other.close();
  }
  expect(errors).toEqual([]);
});

test("a reason is required, and the IT admin cannot open the overrides screen", async ({ page, browser }) => {
  await signIn(page, "admin", SUPER.email, SUPER.password);
  const id = await itAdminId(page.context().request);
  await signIn(page, "admin", SUPER.email, SUPER.password);
  await page.goto(`/admin/permissions?tab=user&user=${id}`);
  await page.getByRole("combobox", { name: "Payments: Add override" }).selectOption("allow");
  await page.getByRole("button", { name: "Save overrides" }).click();
  await expect(page.locator(".form-error")).toHaveText(/^Give a reason for each override\.\s*$/);

  const other = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const itPage = await other.newPage();
  await signIn(itPage, "it", IT_ADMIN.email, IT_ADMIN.password);
  await itPage.goto(`/admin/permissions?tab=user&user=${id}`);
  await expect(itPage.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  expect((await itPage.request.get(`/api/v1/admin/users/${id}/permissions`)).status()).toBe(403);
  await other.close();
});

for (const [name, width, height] of [["mobile", 375, 812], ["tablet", 768, 1024]] as const) {
  test(`the By user tab fits a ${name} screen without sideways page scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await signIn(page, "admin", SUPER.email, SUPER.password);
    const id = await itAdminId(page.context().request);
    await signIn(page, "admin", SUPER.email, SUPER.password);
    await page.goto(`/admin/permissions?tab=user&user=${id}`);
    await expect(page.getByRole("region", { name: /Permission overrides for/ })).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
  });
}
