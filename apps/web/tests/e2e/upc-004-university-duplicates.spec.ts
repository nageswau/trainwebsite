import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-004 (AC1-AC5, EVID-020 §26): a partnership head searching before adding sees the existing university, a lower-case duplicate is
// blocked with the panel and added only with a reason; the same name in another country is fine; a College BDM adding the same
// university meets the master's panel and links to it; the master then lists the BDM organization. Throwaway accounts via the admin API.

async function superAdmin(page: Page) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function countryId(page: Page, name: string): Promise<string> {
  const page_ = await (await page.request.get(`/api/v1/lookups/countries?q=${encodeURIComponent(name)}&limit=5`)).json();
  return page_.items.find((c: { label: string }) => c.label === name).id;
}

async function startAdding(page: Page, name: string, country: string) {
  await page.goto("/partnership/universities/new");
  await page.getByLabel("University name (required)").fill(name);
  const combo = page.getByRole("combobox", { name: "Country (required)" });
  await combo.fill(country);
  await page.getByRole("option", { name: new RegExp(`^${country}`) }).first().click();
  await page.getByLabel("City (required)").fill("Leeds");
}

test("head: search before adding, blocked duplicate, override with a reason", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const name = `E2E Duplicate University ${stamp}`;
  await superAdmin(page);
  const head = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc004-h-${stamp}@example.local` },
  })).json();
  const uk = await countryId(page, "United Kingdom");
  const existing = await (await page.request.post("/api/v1/partnership/universities", {
    data: { name, country_id: uk, city: "London", existing_relationship: "existing" },
  })).json();
  await activateWithToken(page.request, head.development_welcome_token);

  await signIn(page, "admin", head.email, "/partnership/head/team");
  await startAdding(page, `  ${name.toLowerCase()} `, "United Kingdom");
  const panel = page.getByRole("status").filter({ hasText: "Already in the University Master" });
  await expect(panel).toBeVisible();
  await expect(panel).toContainText(existing.university.university_code);
  await expect(panel).toContainText("Existing relationship");

  // AC1: saving anyway is blocked with the panel.
  await page.getByRole("button", { name: "Add university" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "This university is already in the University Master" });
  await expect(alert).toBeVisible();
  await expect(alert.getByRole("link", { name: new RegExp(existing.university.university_code) })).toBeVisible();
  await expect(page).toHaveURL(/\/partnership\/universities\/new$/);

  // AC4: the head adds it anyway with a reason.
  await page.getByLabel("Reason for adding it anyway (required)").fill("Separate campus with its own partnership office");
  await page.getByRole("button", { name: "Add anyway" }).click();
  await page.waitForURL(/\/partnership\/universities\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 2 })).toContainText(name.toLowerCase());

  // AC3: the same name in another country is a new university, no panel.
  await startAdding(page, `${name} Dubai`, "United Kingdom");
  await expect(page.getByRole("status").filter({ hasText: "Already in the University Master" })).toHaveCount(0);
  const ireland = await page.request.post("/api/v1/partnership/universities", { data: { name, country_id: await countryId(page, "Ireland"), city: "Dublin" } });
  expect(ireland.status()).toBe(201);

  // The panel fits a phone (no sideways scroll).
  await page.setViewportSize({ width: 375, height: 800 });
  await startAdding(page, name, "United Kingdom");
  await expect(page.getByRole("status").filter({ hasText: "Already in the University Master" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("BDM: a University organization meets the master's panel and links to it", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const name = `E2E Linked University ${stamp}`;
  await superAdmin(page);
  const uni = (await (await page.request.post("/api/v1/partnership/universities", {
    data: { name, country_id: await countryId(page, "United Kingdom"), city: "London" },
  })).json()).university;
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E BDM Manager ${stamp}`, email: `upc004-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "bdm", full_name: `E2E College BDM ${stamp}`, email: `upc004-b-${stamp}@example.local`,
      bdm_profile: { bdm_type: "college", employee_id: `U4-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  await page.goto("/bdm/organizations/new");
  await page.getByLabel("Type (required)").selectOption("university");
  await page.getByLabel("Organization name (required)").fill(name.toUpperCase());
  await page.getByLabel("City (required)").fill("London");
  await page.getByLabel("Contact name (required)").first().fill("Ms Clarke");
  await page.getByRole("button", { name: "Save organization" }).click();

  // AC2: the same panel, without links into the master.
  const alert = page.getByRole("alert").filter({ hasText: "Already in the University Master" });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText(uni.university_code);
  await expect(alert.getByRole("link")).toHaveCount(0);
  await alert.getByRole("button", { name: `Link to ${uni.university_code} and save` }).click();
  await page.waitForURL(/\/bdm\/organizations\/[0-9a-f-]+\?created=1/);
  const details = page.getByRole("region", { name: "Details" });
  await expect(details).toContainText(`${uni.university_code} · ${name}, United Kingdom`);
  const orgCode = (await page.locator(".eyebrow").first().textContent())!.split(" · ")[0];

  // AC5: the master lists the linked organization.
  await superAdmin(page);
  await page.goto(`/partnership/universities/${uni.id}`);
  const linked = page.getByRole("region", { name: "Linked BDM organizations" });
  await expect(linked).toContainText(orgCode);
  await expect(linked).toContainText(`BDM E2E College BDM ${stamp}`);
});
