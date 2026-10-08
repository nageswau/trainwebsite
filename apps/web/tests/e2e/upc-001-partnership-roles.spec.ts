import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-001 (AC1, AC3, AC4, PU1, PU8): a Super Admin creates a partnership head (generic Users API) and a manager (Partnership managers
// page); each activates from its link and lands on its own page; the manager edits its mobile; the head sees it in their team.
// Throwaway accounts via the real admin API.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "overseas" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function createHead(page: Page, stamp: number) {
  const response = await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc001-h-${stamp}@example.local` },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test("head and manager: create on the page, activate, land, edit mobile, team", async ({ page }) => {
  test.setTimeout(60_000);
  const stamp = Date.now();
  await superAdmin(page);
  const head = await createHead(page, stamp);

  await page.goto("/admin/partnership-managers");
  await page.getByLabel("Full name (required)").fill(`E2E Manager ${stamp}`);
  await page.getByLabel("Email (required)").fill(`upc001-m-${stamp}@example.local`);
  await page.getByLabel("Employee ID (required)").fill(`UPC-${stamp}`);
  const picker = page.getByRole("combobox", { name: "Reporting head (required)" });
  await picker.fill(`E2E Head ${stamp}`);
  await page.getByRole("option", { name: new RegExp(`E2E Head ${stamp}`) }).click();
  const created = page.waitForResponse((r) => r.url().endsWith("/api/v1/admin/users") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Create partnership manager" }).click();
  const manager = await (await created).json();
  await expect(page.locator("#partnership-create-feedback")).toContainText("Partnership manager created.");
  await expect(page.getByRole("region", { name: "Partnership managers" }).getByText(`UPC-${stamp}`)).toBeVisible();
  expect(manager.division).toBe("overseas");
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, manager.development_welcome_token);
  await signIn(page, "overseas", manager.email, "/partnership/dashboard");
  await expect(page.locator("dd", { hasText: `UPC-${stamp}` })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Coming soon to your CRM" })).toBeVisible();
  await page.goto("/partnership/profile");
  await page.getByLabel("Mobile", { exact: true }).fill("+91 98765 11111");
  await page.getByRole("button", { name: "Save mobile" }).click();
  await expect(page.getByText("Mobile saved.")).toBeVisible();
  await expect(page.locator("dd", { hasText: "+91 98765 11111" })).toBeVisible();
  // N3: a manager calling the head route gets the API's 403.
  expect((await page.request.get("/api/v1/partnership/head/team")).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");

  // The head's welcome link opens the admin portal's own reset page.
  await page.goto(`/admin/reset-password?token=${head.development_welcome_token}`);
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL("**/admin/login");
  await signIn(page, "admin", head.email, "/partnership/head/team");
  await expect(page.getByRole("region", { name: "Team" }).getByText(`E2E Manager ${stamp}`)).toBeVisible();
});

test("signed-out /partnership visits go to the right sign-in (PU1)", async ({ page }) => {
  await page.goto("/partnership/profile");
  await page.waitForURL("**/overseas/login?next=%2Fpartnership%2Fprofile");
  await page.goto("/partnership/head/team");
  await page.waitForURL("**/admin/login?next=%2Fpartnership%2Fhead%2Fteam");
});

test("a head at the wrong portal gets the correct-portal message (AC3)", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const head = await createHead(page, stamp);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, head.development_welcome_token);
  await page.goto("/overseas/login");
  await page.fill("#login-email", head.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await expect(page.getByText(/sign in at \/admin\/login/)).toBeVisible();
});

test("Partnership managers page works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await createHead(page, Date.now());
  await page.goto("/admin/partnership-managers");
  await expect(page.getByRole("heading", { name: "Create partnership manager" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create partnership manager" })).toBeEnabled();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
