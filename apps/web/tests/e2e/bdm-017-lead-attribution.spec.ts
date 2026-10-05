import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-017 (AC1, AC3, AC4): a College BDM adds leads on an organization (keyboard only for one; a same-email duplicate is confirmed), the
// exact count shows on the profile; the admin filters the lead list by the organization, links a lead to a student and unlinks it; nothing
// overflows at 320 / 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("BDM lead attribution: add, duplicate, count, admin filter, link and unlink", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm017-m-${stamp}@example.com` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm017-b-${stamp}@example.com`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E17-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  const student = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "it_student", division: "it", full_name: `E2E Student ${stamp}`, email: `bdm017-s-${stamp}@example.com` },
  })).json();
  for (const account of [manager, bdm, student]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  })).json()).organization;

  // AC1: add a lead on the profile.
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("heading", { name: "Leads (0)" })).toBeVisible();
  await page.getByRole("button", { name: "Add lead" }).click();
  await page.getByLabel("Student name (required)").fill("Asha Nair");
  await page.getByLabel("Email (required)").fill(`asha-${stamp}@example.com`);
  await page.getByLabel("Interest (required)").fill("B.Tech CSE");
  await page.getByRole("button", { name: "Save lead" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Lead added." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Leads (1)" })).toBeVisible();

  // L8: the same email again warns; Save anyway keeps both. Keyboard only.
  await page.getByRole("button", { name: "Add lead" }).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.type("Asha N");
  await page.getByLabel("Email (required)").focus();
  await page.keyboard.type(`ASHA-${stamp}@example.com`);
  await page.getByLabel("Interest (required)").focus();
  await page.keyboard.type("B.Tech");
  await page.getByRole("button", { name: "Save lead" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Possible duplicate" })).toContainText("Asha Nair");
  await page.keyboard.press("Enter"); // "Save anyway" has focus
  await expect(page.getByRole("heading", { name: "Leads (2)" })).toBeVisible(); // AC4: the exact count
  await noOverflow(page);

  // AC1 + AC3: the admin sees the organization, filters to it, links a lead to the student and unlinks it.
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  await page.goto("/it/admin/leads");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage leads" }) });
  await panel.getByLabel("Organization").selectOption({ label: `${org.code} · ${org.name}` });
  await expect(panel.getByRole("rowheader")).toHaveText(["Asha N", "Asha Nair"]);
  const row = panel.locator("tr", { has: page.getByRole("rowheader", { name: "Asha Nair", exact: true }) });
  await expect(row).toContainText(`${org.code} · ${org.name}`);
  await row.getByRole("button", { name: "Link student to Asha Nair" }).click();
  await row.getByLabel("Student account email for Asha Nair").fill(student.email);
  await row.getByRole("button", { name: "Link", exact: true }).click();
  await expect(row.getByRole("status")).toHaveText("Student linked.");
  await expect(row).toContainText(`E2E Student ${stamp} (${student.email})`);
  await row.getByRole("button", { name: "Unlink student from Asha Nair" }).click();
  await row.getByRole("button", { name: "Yes, unlink" }).click();
  await expect(row.getByRole("button", { name: "Link student to Asha Nair" })).toBeVisible();
  await noOverflow(page);
});
