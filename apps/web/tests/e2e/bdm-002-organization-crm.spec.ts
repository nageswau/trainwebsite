import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-002 (AC1, AC2, AC4, AC5a, AC6, AC9): a College BDM adds an organization with two contacts, meets the duplicate warning and
// saves anyway; a second BDM of the type can read but not edit; the manager reassigns one; the BDM archives the other and the
// manager restores it; the list fits a phone. Throwaway accounts through the real admin API (the bdm-001 spec's pattern).

async function superAdmin(page: Page) {
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

async function addOrganization(page: Page, name: string) {
  await page.goto("/bdm/organizations/new");
  await page.getByLabel("Type (required)").selectOption("college");
  await page.getByLabel("Organization name (required)").fill(name);
  await page.getByLabel("City (required)").fill("Kochi");
  await page.getByLabel("Contact name (required)").first().fill("Dr Rao");
  await page.getByLabel("Role").first().selectOption("principal");
}

test("BDM organization CRM: add, duplicate warning, read-only peer, reassign, archive and restore", async ({ page }) => {
  test.setTimeout(120_000); // four sign-ins across three accounts (the AGN-003/004/008 journeys use the same)
  const stamp = Date.now();
  const name = `E2E College ${stamp}`;
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm002-m-${stamp}@example.local` },
  })).json();
  const bdm = (n: number) =>
    page.request.post("/api/v1/admin/users", {
      data: {
        role: "bdm", full_name: `E2E BDM${n} ${stamp}`, email: `bdm002-b${n}-${stamp}@example.local`,
        bdm_profile: { bdm_type: "college", employee_id: `E2E2-${n}-${stamp}`, reporting_manager_user_id: manager.id },
      },
    });
  const one = await (await bdm(1)).json();
  const two = await (await bdm(2)).json();
  for (const account of [manager, one, two]) await activateWithToken(page.request, account.development_welcome_token);

  // AC1: BDM 1 adds a college with a Principal and a Placement Officer.
  await signIn(page, "it", one.email, "/bdm/my-day");
  await page.getByRole("link", { name: "Organizations" }).first().click();
  await page.waitForURL("**/bdm/organizations");
  await addOrganization(page, name);
  await page.getByRole("button", { name: "Add contact" }).click();
  await page.getByLabel("Contact name (required)").nth(1).fill("Ms Iyer");
  await page.getByLabel("Role").nth(1).selectOption("placement_officer");
  await page.getByRole("button", { name: "Save organization" }).click();
  await page.waitForURL(/\/bdm\/organizations\/[0-9a-f-]+\?created=1/);
  await expect(page.getByRole("status")).toContainText(/Organization ORG-\d{6,} created\./);
  const firstUrl = page.url().split("?")[0];
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByText("Dr Rao")).toBeVisible();
  await expect(page.getByRole("list", { name: "Contacts" }).getByRole("listitem").filter({ hasText: "Ms Iyer" })).toHaveCount(1);

  // AC2: the same name again warns; Save anyway creates a second one.
  await addOrganization(page, name.toUpperCase());
  await page.getByRole("button", { name: "Save organization" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "A similar organization already exists" })).toBeVisible(); // Next adds its own empty route-announcer alert
  await page.getByRole("button", { name: "Save anyway" }).click();
  await page.waitForURL(/\?created=1/);
  const secondUrl = page.url().split("?")[0];

  // AC3: BDM 2 sees both in the module but cannot edit them.
  await signIn(page, "it", two.email, "/bdm/my-day");
  await page.goto(`/bdm/organizations?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("region", { name: "Organizations" }).getByRole("link")).toHaveCount(2);
  await page.goto(firstUrl);
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);

  // AC4: the manager reassigns the second organization to BDM 2.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto(secondUrl.replace("/bdm/organizations/", "/bdm/manager/organizations/"));
  const picker = page.getByRole("combobox", { name: "Reassign to" });
  await picker.fill("BDM2");
  await page.getByRole("option", { name: new RegExp(`E2E BDM2 ${stamp}`) }).click();
  await page.getByRole("button", { name: "Reassign", exact: true }).click();
  await page.getByRole("button", { name: "Yes, reassign" }).click();
  await expect(page.getByRole("status")).toContainText(`Reassigned to E2E BDM2 ${stamp}.`);

  // AC5a: BDM 1 archives the first; it is hidden by default and shown with "Show archived".
  await signIn(page, "it", one.email, "/bdm/my-day");
  await page.goto(firstUrl);
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Yes, archive" }).click();
  await expect(page.getByRole("status")).toContainText("Organization archived.");
  await page.goto(`/bdm/organizations?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("region", { name: "Organizations" }).getByRole("link")).toHaveCount(1);
  await page.getByLabel("Show archived").click(); // URL-driven: checked once the navigation lands
  await expect(page.getByLabel("Show archived")).toBeChecked();
  await expect(page.getByRole("region", { name: "Organizations" }).getByText("Archived")).toBeVisible();

  // The manager restores it (BDM 1 still reports to them).
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto(firstUrl.replace("/bdm/organizations/", "/bdm/manager/organizations/"));
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByRole("status")).toContainText("Organization restored.");

  // AC9: the BDM list fits a phone (the table scrolls inside its own region, never the page).
  await signIn(page, "it", one.email, "/bdm/my-day");
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/bdm/organizations?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("region", { name: "Organizations" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("signed-out organization pages go to the right sign-in", async ({ page }) => {
  await page.goto("/bdm/organizations");
  await page.waitForURL("**/bdm/sign-in?next=%2Fbdm%2Forganizations");
  await page.goto("/bdm/manager/organizations");
  await page.waitForURL("**/admin/login?next=%2Fbdm%2Fmanager%2Forganizations");
});
