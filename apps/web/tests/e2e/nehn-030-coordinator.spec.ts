import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// nehn-030 (DEC-SCOPE-293, RBAC §2.204): an IT admin creates a coordinator through the real Create user form; the coordinator signs in
// at /it, lands on its own portal (Dashboard, Certificates) and is refused everything else. The Certificates section follows the
// `certificates.view` grant, which a test switches off only for as long as the check needs and always restores.

const SUPER = { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" };
const SEED_COORDINATOR = "coordinator@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setCoordinatorGrants(request: APIRequestContext, permissions: string[]) {
  await request.post("/api/v1/auth/login", { data: SUPER });
  try {
    const response = await request.put("/api/v1/admin/roles/coordinator/permissions", { data: { permissions } });
    expect(response.status(), await response.text()).toBe(200);
  } finally {
    await request.post("/api/v1/auth/logout");
  }
}

test.describe.configure({ mode: "serial" });

test("an IT admin creates a coordinator who signs in to the Certificates portal", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page, "itadmin@edusphere.local", "Demo@123");
  await page.goto("/it/admin/users");
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Create user" }) });
  const email = `e2e-coordinator-${Date.now()}@example.com`;
  await form.locator('input[name="full_name"]').fill("E2E Coordinator");
  await form.locator('input[name="email"]').fill(email);
  await form.locator('select[name="division"]').selectOption("it");
  await form.locator('select[name="role"]').selectOption("coordinator");
  const created = await createAndActivateFromUi(page, ".action-card:has(h3:has-text('Create user')) button:has-text('Create user')", "/api/v1/admin/users");
  expect(created.role).toBe("coordinator");
  await expect(form.getByText("User created.")).toBeVisible();

  const context = await browser.newContext();
  const coordinator = await context.newPage();
  coordinator.on("pageerror", (e) => errors.push(e.message));
  await signIn(coordinator, email, E2E_PASSWORD);
  await expect(coordinator).toHaveURL(/\/it\/coordinator\/dashboard$/);
  await expect(coordinator.getByRole("heading", { name: "Coordinator Dashboard" })).toBeVisible();
  await expect(coordinator.getByText("Certificates issued").first()).toBeVisible();
  const nav = coordinator.getByRole("navigation").first();
  await expect(nav.getByRole("link", { name: "Certificates" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Users" })).toHaveCount(0);

  await nav.getByRole("link", { name: "Certificates" }).click();
  await expect(coordinator).toHaveURL(/\/it\/coordinator\/certificates$/);
  await expect(coordinator.getByRole("heading", { name: "Certificates", exact: true })).toBeVisible();
  for (const width of [375, 768, 1280]) {
    await coordinator.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(coordinator), `side scroll at ${width}px`).toBe(true);
  }
  await context.close();
  expect(errors).toEqual([]);
});

test("the coordinator is refused admin, finance and other portals", async ({ page }) => {
  await signIn(page, SEED_COORDINATOR, "Demo@123");
  for (const path of ["/api/v1/admin/users", "/api/v1/admin/payments", "/api/v1/portal/it/admin/dashboard", "/api/v1/portal/it/trainer/dashboard"]) {
    expect((await page.request.get(path)).status(), path).toBe(403);
  }
  await page.goto("/it/admin/users");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to your dashboard" })).toHaveAttribute("href", "/it/coordinator/dashboard");
  const missing = await page.goto("/it/coordinator/users");
  expect(missing?.status()).toBe(404);
});

test("another IT role cannot open the coordinator portal", async ({ page }) => {
  await signIn(page, "trainer@edusphere.local", "Demo@123");
  await page.goto("/it/coordinator/certificates");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

// `request` is its own cookie jar, so the super admin's sign-in there never touches the coordinator's open session in `page`.
test("switching certificates.view off closes Certificates on the next request; switching it on restores it", async ({ page, request }) => {
  await signIn(page, SEED_COORDINATOR, "Demo@123");
  await setCoordinatorGrants(request, []);
  try {
    await page.goto("/it/coordinator/certificates");
    await expect(page.getByText("You do not have permission to view certificates")).toBeVisible();
    await page.goto("/it/coordinator/dashboard");
    await expect(page.getByText("Your Certificates permission is switched off")).toBeVisible();
  } finally {
    await setCoordinatorGrants(request, ["certificates.view"]);
  }
  await page.goto("/it/coordinator/certificates");
  await expect(page.getByRole("heading", { name: "Certificates", exact: true })).toBeVisible();
});
