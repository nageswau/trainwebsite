import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-005 (DEC-SCOPE-362): the IT Admin renames Interested to "Course Interested" and turns Not Eligible off on Status Labels; an IT
// telecaller then sees the new word in the stage picker, on the lead page, in the list and its Stage filter, and is no longer offered Not
// Eligible. Throwaway accounts; the shared labels are put back to the defaults at the end (other specs read the default words).
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const DEFAULTS = [
  ["interested", { label: "Interested", sort_order: 60, enabled: true }],
  ["not_eligible", { label: "Not Eligible", sort_order: 140, enabled: true }],
] as const;

test("the IT Admin renames and turns off lead stages and the IT telecaller's screens follow", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const admin = await post({ role: "it_admin", division: "it", full_name: `E2E SL Admin ${stamp}`, email: `itc005-a-${stamp}@example.local` });
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E SL Manager ${stamp}`, email: `itc005-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E SL Telecaller ${stamp}`, email: `itc005-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `SL-${stamp}`, reporting_manager_user_id: manager.id },
  });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, admin.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  try {
    // the IT Admin's page: rename (+ case) and turn off a chosen outcome
    await signIn(page, "it", admin.email, E2E_PASSWORD, "/it/admin/dashboard");
    await page.getByRole("navigation").getByRole("link", { name: "Status Labels" }).first().click();
    await expect(page).toHaveURL(/\/it\/admin\/status-labels$/);
    await page.getByRole("button", { name: "Edit Interested" }).click();
    await page.getByLabel("Label (required)").fill("Course Interested");
    await page.getByRole("button", { name: "Save Interested label" }).click();
    await expect(page.getByText("Saved Course Interested.")).toBeVisible();
    await page.getByRole("button", { name: "Turn off Not Eligible" }).click();
    await expect(page.getByText(/^Turned off Not Eligible\./)).toBeVisible();
    await expect(page.getByRole("button", { name: "Turn on Not Eligible" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Turn off Contacted" })).toHaveCount(0); // a system state is never turned off
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await noSideScroll(page)).toBe(true);
    await page.setViewportSize({ width: 1280, height: 800 });

    // the IT telecaller's screens
    await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
    const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
    const name = `SL Lead ${stamp}`;
    const created = await page.request.post("/api/v1/telecaller/leads", {
      data: { name, email: `itc005-l-${stamp}@example.local`, phone: `7${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`, product_id: products[0].id, source: "walk_in" },
    });
    expect(created.status(), await created.text()).toBe(201);
    const id = (await created.json()).id as string;

    await page.goto(`/telecaller/leads/${id}`);
    await page.getByRole("button", { name: `Change stage for ${name}` }).click();
    const picker = page.getByLabel(`New stage for ${name}`);
    await expect(picker.locator("option", { hasText: "Course Interested" })).toHaveCount(1);
    await expect(picker.locator("option", { hasText: /^Not Eligible$/ })).toHaveCount(0); // AC2: not offered
    await picker.selectOption("interested");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Stage updated.")).toBeVisible();
    await page.reload();
    await expect(page.getByRole("main")).toContainText("Stage: Course Interested");

    await page.goto("/telecaller/leads");
    const row = page.locator("tr", { hasText: name });
    await expect(row).toContainText("Course Interested"); // AC1: the list
    await page.getByLabel("Stage").selectOption("interested");
    await expect(page).toHaveURL(/status=interested/);
    await expect(page.getByLabel("Stage").locator("option:checked")).toHaveText("Course Interested");
    await expect(page.getByLabel("Stage").locator("option", { hasText: /^Not Eligible$/ })).toHaveCount(1); // filters keep it (history)

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.locator("tr", { hasText: name })).toContainText("Course Interested");
    expect(await noSideScroll(page)).toBe(true);
    expect(consoleErrors).toEqual([]);
  } finally {
    await page.context().clearCookies();
    const login = await page.request.post("/api/v1/auth/login", { data: { email: admin.email, password: E2E_PASSWORD, division: "it" } });
    expect(login.ok(), await login.text()).toBe(true);
    for (const [code, body] of DEFAULTS) {
      const reset = await page.request.put(`/api/v1/admin/it/status-labels/lead/${code}`, { data: body });
      expect(reset.status(), await reset.text()).toBe(200);
    }
  }
});
