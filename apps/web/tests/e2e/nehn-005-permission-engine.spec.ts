import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// nehn-005 (DEC-SCOPE-281): the permission engine is API-only (the matrix UI is nehn-006). The existing pages keep working on the seed
// grants, and a grant super_admin changes applies to an open session on its next request. Grants are role-wide, so a test changes them
// only for a role no other spec relies on (accountant), or for as short a window as the browser check needs (telecaller_manager's
// download), and always restores them.

const SUPER = { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" };
const REPORTS = ["reports.telecaller.download", "reports.telecaller.view"];
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function asSuper(request: APIRequestContext, run: () => Promise<void>) {
  await request.post("/api/v1/auth/login", { data: SUPER });
  try {
    await run();
  } finally {
    await request.post("/api/v1/auth/logout");
  }
}

async function setGrants(request: APIRequestContext, role: string, permissions: string[]) {
  await asSuper(request, async () => {
    const response = await request.put(`/api/v1/admin/roles/${role}/permissions`, { data: { permissions } });
    expect(response.status(), await response.text()).toBe(200);
  });
}

async function signIn(page: Page, portal: "it" | "admin", email: string, password = E2E_PASSWORD) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test.describe.configure({ mode: "serial" });

test("Payment Management works on the seed, and a grant change applies to an open session", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // The page is the Super Admin's (the UI gate is unchanged); its forms post through payments.add.
  await signIn(page, "admin", SUPER.email, SUPER.password);
  await page.goto("/admin/payments");
  await expect(page.getByRole("heading", { name: "Payment Management" })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  const create = page.locator("form").filter({ hasText: "Create payment due" });
  await create.getByLabel("User reference").fill("00000000-0000-0000-0000-000000000000");
  await create.getByLabel("Amount").fill("10");
  await create.getByRole("button", { name: "Create payment due" }).click();
  await expect(create.getByText("User not found")).toBeVisible();

  // The seed: an IT admin holds the payment keys; an accountant holds none.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", "itadmin@edusphere.local", "Demo@123");
  expect((await (await page.request.get("/api/v1/auth/me/permissions")).json()).permissions).toContain("payments.view");
  expect((await page.request.get("/api/v1/admin/payments")).status()).toBe(200);

  const stamp = Date.now();
  let email = "";
  await asSuper(page.request, async () => {
    email = (await createAndActivate(page.request, "/api/v1/admin/users", {
      role: "accountant", division: "global", full_name: `E2E Grant Accountant ${stamp}`, email: `n005-a-${stamp}@example.local`,
    })).email;
  });
  await signIn(page, "admin", email);
  expect((await page.request.get("/api/v1/admin/payments")).status()).toBe(403);
  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    await setGrants(admin.request, "accountant", ["payments.view"]);
    expect((await page.request.get("/api/v1/admin/payments")).status()).toBe(200);
    expect((await (await page.request.get("/api/v1/auth/me/permissions")).json()).permissions).toEqual(["payments.view"]);
  } finally {
    await setGrants(admin.request, "accountant", []);
    await admin.close();
  }
  const refused = await page.request.get("/api/v1/admin/payments");
  expect(refused.status()).toBe(403);
  expect(await refused.json()).toEqual({ detail: "Admin role required" });
  expect(errors).toEqual([]);
});

async function managerWithALead(request: APIRequestContext, stamp: number): Promise<string> {
  let email = "";
  await asSuper(request, async () => {
    const manager = await createAndActivate(request, "/api/v1/admin/users", {
      role: "telecaller_manager", division: "global", full_name: `E2E Grant Manager ${stamp}`, email: `n005-m-${stamp}@example.local`,
    });
    const caller = await (await request.post("/api/v1/admin/users", {
      data: {
        role: "telecaller", full_name: `E2E Grant Telecaller ${stamp}`, email: `n005-t-${stamp}@example.local`,
        telecaller_profile: { team: "it", employee_id: `N5-${stamp}`, reporting_manager_user_id: manager.id },
      },
    })).json();
    const product = await (await request.post("/api/v1/telecaller/products", { data: { group: "it", name: `E2E Grant Course ${stamp}` } })).json();
    const lead = await request.post("/api/v1/telecaller/leads", {
      data: { name: `Grant Lead ${stamp}`, phone: `9${String(stamp).slice(-8)}0`, product_id: product.id, source: "instagram", division: "it" },
    });
    expect(lead.status(), await lead.text()).toBe(201);
    const assigned = await request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: [(await lead.json()).id], telecaller_user_id: caller.id } });
    expect(assigned.status()).toBe(200);
    email = manager.email;
  });
  return email;
}

test("a manager still reads the reports when only the download is revoked", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const email = await managerWithALead(page.request, Date.now());
  await signIn(page, "admin", email);
  await page.goto("/telecaller/manager/reports");
  await expect(page.getByRole("heading", { name: "Lead Source Report" })).toBeVisible();

  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    await setGrants(admin.request, "telecaller_manager", ["reports.telecaller.view"]);
    await page.getByRole("button", { name: "Download CSV" }).click();
    await expect(page.getByText("You don't have permission to download telecaller reports")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Lead Source Report" })).toBeVisible();
  } finally {
    await setGrants(admin.request, "telecaller_manager", REPORTS);
    await admin.close();
  }
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^telecaller-source-.*\.csv$/);

  for (const [width, height] of [[768, 1024], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.reload();
    await expect(page.getByRole("heading", { name: "Lead Source Report" })).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
  }
});

test("only super_admin reaches the permission endpoints", async ({ page }) => {
  await signIn(page, "it", "itadmin@edusphere.local", "Demo@123");
  expect((await page.request.get("/api/v1/admin/permissions/catalogue")).status()).toBe(403);
  expect((await page.request.put("/api/v1/admin/roles/it_admin/permissions", { data: { permissions: [] } })).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");
  expect((await page.request.get("/api/v1/auth/me/permissions")).status()).toBe(401);
  await asSuper(page.request, async () => {
    expect((await page.request.put("/api/v1/admin/roles/super_admin/permissions", { data: { permissions: [] } })).status()).toBe(409);
    expect((await page.request.put("/api/v1/admin/roles/it_admin/permissions", { data: { permissions: ["payments.fly"] } })).status()).toBe(422);
  });
});
