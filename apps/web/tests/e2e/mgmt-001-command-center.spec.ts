import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// mgmt-001 (AC1, AC3, AC4, M13): a Super Admin creates a partner from the Users page and an accountant through the admin API; each
// activates from its link, signs in at /admin and lands on the Command Center with its own tier. Throwaway accounts via the real API.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/management");
}

test("signed out, /management sends you to the admin sign-in with next (AC4)", async ({ page }) => {
  await page.goto("/management");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement$/);
});

test("partner and accountant: create, activate, sign in at /admin, land on their tier of the Command Center", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  await superAdmin(page);

  await page.goto("/admin/users");
  const form = page.locator("form", { has: page.getByRole("button", { name: "Create user" }) });
  await form.getByLabel("Full name").fill(`E2E Partner ${stamp}`);
  await form.getByLabel("Email").fill(`mgmt001-p-${stamp}@example.local`);
  await form.getByLabel("Division").selectOption("global");
  await form.getByLabel("Role").selectOption("partner");
  const created = page.waitForResponse((r) => r.url().endsWith("/api/v1/admin/users") && r.request().method() === "POST");
  await form.getByRole("button", { name: "Create user" }).click();
  const partner = await (await created).json();
  expect(partner.role).toBe("partner");
  expect(partner.division).toBe("global");

  const accountantResponse = await page.request.post("/api/v1/admin/users", {
    data: { role: "accountant", division: "global", full_name: `E2E Accountant ${stamp}`, email: `mgmt001-a-${stamp}@example.local` },
  });
  expect(accountantResponse.status()).toBe(201);
  const accountant = await accountantResponse.json();

  // The super admin sees the operational pillars only (MG10).
  await page.goto("/management");
  await expect(page.getByRole("heading", { level: 2, name: "Management Command Center" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Students" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Finance" })).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, partner.development_welcome_token);
  await signIn(page, partner.email);
  await expect(page.getByRole("heading", { level: 2, name: "Management Command Center" })).toBeVisible();
  for (const title of ["Students", "Sales", "Finance", "People", "Partnerships", "Business Intelligence"]) {
    await expect(page.getByRole("region", { name: title })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "Finance" }).getByText("Partner capital accounts")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, accountant.development_welcome_token);
  await signIn(page, accountant.email);
  const finance = page.getByRole("region", { name: "Finance" });
  await expect(finance.getByText("Salaries")).toBeVisible();
  await expect(finance.getByText("Investments & ROI")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Students" })).toHaveCount(0);
  // An accountant is not an admin (MG1/MG2).
  expect((await page.request.get("/api/v1/admin/users")).status()).toBe(403);
});

test("an IT admin cannot create a partner (AC2) and cannot open the Command Center", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
  const refused = await page.request.post("/api/v1/admin/users", {
    data: { role: "partner", division: "global", full_name: "Nope", email: `mgmt001-x-${Date.now()}@example.local` },
  });
  expect(refused.status()).toBe(403);
  await page.goto("/management");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("Management access required")).toBeVisible();
});
