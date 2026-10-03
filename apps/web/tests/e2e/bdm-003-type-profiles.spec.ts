import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-003 (AC1, AC2, AC8, AC10; spec §8.3): a School BDM adds a school with Board, grades, an address and a Principal using only the
// keyboard; the detail shows the school details; the Board filter finds it; at 320 px the form has no sideways scroll; a College BDM's
// form shows College details and no Board. Throwaway accounts through the real admin API (the bdm-002 spec's pattern).

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/bdm/my-day");
}

/** Keyboard only: focus the control, then type (type-ahead picks an option in a closed native select). */
async function typeInto(page: Page, label: string, text: string) {
  await page.getByLabel(label, { exact: true }).focus();
  await page.keyboard.type(text);
}

async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

test("bdm-003 type profiles: school details by keyboard, Board filter, 320 px, college form", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (
    await page.request.post("/api/v1/admin/users", {
      data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm003-m-${stamp}@example.local` },
    })
  ).json();
  const bdm = async (type: string) =>
    (
      await page.request.post("/api/v1/admin/users", {
        data: {
          role: "bdm", full_name: `E2E ${type} BDM ${stamp}`, email: `bdm003-${type}-${stamp}@example.local`,
          bdm_profile: { bdm_type: type, employee_id: `E2E3-${type}-${stamp}`, reporting_manager_user_id: manager.id },
        },
      })
    ).json();
  const school = await bdm("school");
  const college = await bdm("college");
  for (const account of [manager, school, college]) await activateWithToken(page.request, account.development_welcome_token);

  // AC1 + AC10, keyboard only: no clicks from here to the saved detail page.
  await signIn(page, school.email);
  await page.goto("/bdm/organizations/new");
  const name = `E2E School ${stamp}`;
  await typeInto(page, "Type (required)", "School");
  await expect(page.getByRole("group", { name: "School details" })).toBeVisible();
  await typeInto(page, "Organization name (required)", name);
  await typeInto(page, "City (required)", "Kochi");
  await typeInto(page, "Address", "1 Main Rd");
  await page.keyboard.press("Enter"); // a line break in the textarea, not a submit
  await page.keyboard.type("Kochi");
  await typeInto(page, "Board", "CBSE");
  await typeInto(page, "Lowest grade", "6");
  await typeInto(page, "Highest grade", "12");
  await typeInto(page, "Contact name (required)", "Dr Rao");
  await typeInto(page, "Role", "Principal");
  await page.getByRole("button", { name: "Save organization" }).focus();
  await page.keyboard.press("Enter");
  await page.waitForURL(/\/bdm\/organizations\/[0-9a-f-]+\?created=1/);
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByRole("heading", { name: "School details" })).toBeVisible();
  await expect(details.getByText("6–12")).toBeVisible();
  await expect(details.getByText("CBSE")).toBeVisible();
  await expect(details.getByText("Dr Rao")).toBeVisible();
  expect(await details.getByText("1 Main Rd").textContent()).toBe("1 Main Rd\nKochi");

  // AC8: the Board filter finds it; another board does not.
  await page.goto(`/bdm/organizations?org_type=school&board=CBSE&q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await page.goto(`/bdm/organizations?org_type=school&board=ICSE&q=${encodeURIComponent(name)}`);
  await expect(page.getByText("No organizations match these filters.")).toBeVisible();

  // 320 px: the form with the school section fits.
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/bdm/organizations/new");
  await page.getByLabel("Type (required)").selectOption("school");
  await expect(page.getByRole("group", { name: "School details" })).toBeVisible();
  await noSidewaysScroll(page);

  // AC1 / AC2 in the UI: a College BDM sees College details and no Board.
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, college.email);
  await page.goto("/bdm/organizations/new");
  await page.getByLabel("Type (required)").selectOption("college");
  await expect(page.getByRole("group", { name: "College details" })).toBeVisible();
  await expect(page.getByLabel("Courses", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Board", { exact: true })).toHaveCount(0);
});
