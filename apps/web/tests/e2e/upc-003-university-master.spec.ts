import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-003 (AC1, AC3, AC4, §27): a partnership head adds a university (internal, not public), assigns their manager, publishes it; the
// manager finds it under "Assigned to me" and edits it; a phone-width list has no sideways scroll. Throwaway accounts via the real
// admin API. Public checks call the API directly: the public pages cache for 60 s (revalidate), the API does not.

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

async function provision(page: Page, stamp: number) {
  await superAdmin(page);
  const head = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc003-h-${stamp}@example.local` },
  })).json();
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc003-m-${stamp}@example.local`,
            partnership_profile: { employee_id: `U3-${stamp}`, reporting_head_user_id: head.id } },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, head.development_welcome_token);
  await activateWithToken(page.request, manager.development_welcome_token);
  return { head, manager };
}

async function publicStatus(request: APIRequestContext, slug: string) {
  return (await request.get(`/api/v1/public/universities/${slug}`)).status();
}

async function pick(page: Page, name: string, typed: string, option: RegExp) {
  const combo = page.getByRole("combobox", { name });
  await combo.fill(typed);
  await page.getByRole("option", { name: option }).first().click();
}

test("head adds, assigns and publishes; the manager edits; the list fits a phone", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const name = `E2E University ${stamp}`;
  const { head, manager } = await provision(page, stamp);

  // Head: add from the University Master (AC1). It starts internal (AC3).
  await signIn(page, "admin", head.email, "/partnership/head/team");
  await page.getByRole("link", { name: "University Master" }).first().click();
  await page.waitForURL("**/partnership/universities");
  await page.getByRole("link", { name: "Add university" }).click();
  await page.getByLabel("University name (required)").fill(name);
  await pick(page, "Country (required)", "United Kingdom", /^United Kingdom/);
  await page.getByLabel("City (required)").fill("London");
  await page.getByLabel("Institution type").selectOption("university");
  await page.getByLabel("Website").fill("e2e-university.ac.uk");
  await page.getByLabel("PG").check();
  await page.getByLabel("Popular programme areas").fill("Business, Engineering");
  await page.getByLabel("Priority").selectOption("A");
  await page.getByLabel("Partnership potential").selectOption("high");
  await page.getByLabel(/^Overview/).fill("A research university in London.");
  await page.getByRole("button", { name: "Add ranking" }).click();
  await page.getByLabel("Ranking 1 rank").fill("145");
  await page.getByRole("button", { name: "Add university" }).click();
  await page.waitForURL(/\/partnership\/universities\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.locator("dd", { hasText: /^UNV-\d{6}$/ })).toBeVisible();
  await expect(page.getByText("Internal: only EduSphere staff can see this university.")).toBeVisible();
  const id = page.url().split("/").pop()!;
  const { university } = await (await page.request.get(`/api/v1/partnership/universities/${id}`)).json();
  expect(await publicStatus(page.request, university.slug)).toBe(404);

  // Head: assign their manager (§27), then publish (UM5).
  await pick(page, "Primary manager", `E2E Manager ${stamp}`, new RegExp(`E2E Manager ${stamp}`));
  await page.getByRole("button", { name: "Save managers" }).click();
  await expect(page.locator("dd", { hasText: `E2E Manager ${stamp}` })).toBeVisible();
  await page.getByRole("button", { name: "Publish to catalogue" }).click();
  await expect(page.getByText("Published: students and agents can find this university.")).toBeVisible();
  expect(await publicStatus(page.request, university.slug)).toBe(200);
  await page.request.post("/api/v1/auth/logout");

  // Manager: "Assigned to me" finds it, and the owner can edit (AC4).
  await signIn(page, "overseas", manager.email, "/partnership/dashboard");
  await page.getByRole("link", { name: "University Master" }).first().click();
  await page.getByLabel("Manager").selectOption("me");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await page.waitForURL(/manager=me/);
  await page.getByRole("link", { name }).click();
  await page.getByRole("link", { name: "Edit" }).click();
  await page.getByLabel("City (required)").fill("Cambridge");
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.waitForURL(new RegExp(`/partnership/universities/${id}$`));
  await expect(page.locator("dd", { hasText: /^Cambridge$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish to catalogue" })).toHaveCount(0); // managers do not publish

  // Phone width: the list becomes cards, no sideways scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/partnership/universities?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("link", { name })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("signed out, the University Master asks for the overseas sign-in", async ({ page }) => {
  await page.goto("/partnership/universities");
  await page.waitForURL(/\/overseas\/login\?next=%2Fpartnership%2Funiversities/);
});
