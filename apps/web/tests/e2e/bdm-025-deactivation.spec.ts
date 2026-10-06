import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-025 (AC1, AC2, AC4): a Super Admin deactivates a College BDM, handing their organization to another College BDM in the
// dialog; the row turns Inactive and offers Hand over; a BDM manager with BDMs is deactivated only with a replacement manager.
// Throwaway accounts through the real admin API (bdm-001's pattern).

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function created(request: APIRequestContext, data: Record<string, unknown>) {
  const response = await request.post("/api/v1/admin/users", { data });
  expect(response.status(), await response.text()).toBe(201);
  return { ...data, ...(await response.json()) }; // the create response carries no full_name
}

const bdm = (stamp: number, tag: string, managerId: string) => ({
  role: "bdm", full_name: `E2E 025 ${tag} ${stamp}`, email: `bdm025-${tag}-${stamp}@example.local`,
  bdm_profile: { bdm_type: "college", employee_id: `E25-${tag}-${stamp}`, territory: "Kochi", reporting_manager_user_id: managerId },
});

test("deactivate a BDM with a handover; deactivate their manager with a replacement", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await created(page.request, { role: "bdm_manager", division: "global", full_name: `E2E 025 Manager ${stamp}`, email: `bdm025-m-${stamp}@example.local` });
  const spare = await created(page.request, { role: "bdm_manager", division: "global", full_name: `E2E 025 Spare ${stamp}`, email: `bdm025-s-${stamp}@example.local` });
  const asha = await created(page.request, bdm(stamp, "asha", manager.id));
  const ravi = await created(page.request, bdm(stamp, "ravi", manager.id));

  // AC1: the old PATCH path refuses, with words.
  const patch = await page.request.patch(`/api/v1/admin/users/${asha.id}`, { data: { active: false } });
  expect(patch.status()).toBe(422);

  // Asha (signed in through her welcome link) owns one organization.
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, asha.development_welcome_token);
  expect((await page.request.post("/api/v1/auth/login", { data: { email: asha.email, password: E2E_PASSWORD, division: "it" } })).status()).toBe(200);
  const orgResponse = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E 025 College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  });
  expect(orgResponse.status(), await orgResponse.text()).toBe(201);
  const org = (await orgResponse.json()).organization;
  await page.request.post("/api/v1/auth/logout");
  await superAdmin(page);

  await page.goto(`/admin/bdms?q=${encodeURIComponent(`E25-asha-${stamp}`)}`);
  const row = page.getByRole("row", { name: new RegExp(asha.full_name) });
  await row.getByRole("button", { name: `Deactivate ${asha.full_name}` }).click();
  const group = page.getByRole("group", { name: `Deactivate ${asha.full_name}` });
  await expect(group.getByText("Open work: 1 organization, 0 appointments and 0 follow-ups/tasks.")).toBeVisible();
  const confirm = group.getByRole("button", { name: "Confirm deactivate" });
  await expect(confirm).toBeDisabled(); // AC1: a choice is required
  await group.getByRole("radio", { name: "Hand over to another BDM" }).check();
  await group.getByRole("combobox", { name: "Hand over to" }).fill(`ravi ${stamp}`);
  await group.getByRole("option", { name: new RegExp(ravi.full_name) }).click();
  await confirm.click();
  await expect(page.getByRole("status").filter({
    hasText: `Deactivated ${asha.full_name}. 1 organization, 0 appointments and 0 follow-ups/tasks handed over to ${ravi.full_name}.`,
  })).toBeVisible();
  await expect(row.getByText("Inactive")).toBeVisible();
  // AC2: the organization is Ravi's now.
  const moved = await (await page.request.get(`/api/v1/bdm/organizations/${org.id}`)).json();
  expect(moved.organization.assigned_bdm.id).toBe(ravi.id);
  await row.getByRole("button", { name: `Hand over ${asha.full_name}'s open work` }).click();
  await expect(page.getByText(`${asha.full_name} has no open work to hand over.`)).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  // AC4: the manager still has Ravi (and inactive Asha) -> a replacement is required.
  const managers = page.getByRole("region", { name: "BDM managers" });
  await expect(managers).toBeVisible();
  const managerRow = managers.getByRole("row", { name: new RegExp(manager.full_name) });
  await expect(managerRow.getByText("2 BDMs")).toBeVisible();
  await managerRow.getByRole("button", { name: `Deactivate ${manager.full_name}` }).click();
  const managerGroup = page.getByRole("group", { name: `Deactivate ${manager.full_name}` });
  const confirmManager = managerGroup.getByRole("button", { name: "Confirm deactivate" });
  await expect(confirmManager).toBeDisabled();
  await managerGroup.getByRole("combobox", { name: "Replacement manager" }).fill(`Spare ${stamp}`);
  await managerGroup.getByRole("option", { name: new RegExp(spare.full_name) }).click();
  await confirmManager.click();
  await expect(page.getByRole("status").filter({ hasText: `Deactivated ${manager.full_name}. 2 BDMs now report to ${spare.full_name}.` })).toBeVisible();

  const list = await (await page.request.get(`/api/v1/admin/bdms?q=E25-ravi-${stamp}`)).json();
  expect(list.items[0].id).toBe(ravi.id);
  expect(list.items[0].reporting_manager.id).toBe(spare.id);
});

test("handover dialog on a phone: no sideways scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await created(page.request, { role: "bdm_manager", division: "global", full_name: `E2E 025 PM ${stamp}`, email: `bdm025-pm-${stamp}@example.local` });
  const asha = await created(page.request, bdm(stamp, "phone", manager.id));
  await page.goto(`/admin/bdms?q=${encodeURIComponent(`E25-phone-${stamp}`)}`);
  await page.getByRole("button", { name: `Deactivate ${asha.full_name}` }).click();
  await expect(page.getByRole("group", { name: `Deactivate ${asha.full_name}` }).getByRole("button", { name: "Confirm deactivate" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
