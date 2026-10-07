import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// tel-025 (DEC-SCOPE-104; AC1, AC3, D4, D5): a Super Admin deactivates an IT telecaller, handing their open lead to a teammate in the
// row's group; the plain PATCH path refuses while work exists; the row turns Inactive; a manager with telecallers is deactivated only
// with a replacement. Throwaway accounts through the real admin API (bdm-025's pattern).

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
  return { ...data, ...(await response.json()) } as Record<string, string> & { id: string };
}

const telecaller = (stamp: number, tag: string, managerId: string) => ({
  role: "telecaller", full_name: `E2E 025 ${tag} ${stamp}`, email: `tel025-${tag}-${stamp}@example.local`,
  telecaller_profile: { team: "it", employee_id: `T25-${tag}-${stamp}`, reporting_manager_user_id: managerId },
});

test("deactivate a telecaller with a handover; deactivate their manager with a replacement", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await created(page.request, { role: "telecaller_manager", division: "global", full_name: `E2E 025 Manager ${stamp}`, email: `tel025-m-${stamp}@example.local` });
  const spare = await created(page.request, { role: "telecaller_manager", division: "global", full_name: `E2E 025 Spare ${stamp}`, email: `tel025-s-${stamp}@example.local` });
  const asha = await created(page.request, telecaller(stamp, "asha", manager.id));
  const ravi = await created(page.request, telecaller(stamp, "ravi", manager.id));

  // One open lead on Asha (super_admin assigns it, tel-007).
  const enquiry = await (await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: `E2E 025 Lead ${stamp}`, email: `tel025-l-${stamp}@example.com`, subject: "Python", message: "Please call me." },
  })).json();
  const assigned = await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: [enquiry.id], telecaller_user_id: asha.id } });
  expect(assigned.status(), await assigned.text()).toBe(200);

  // D5: the old PATCH path refuses, with words.
  const patch = await page.request.patch(`/api/v1/admin/users/${asha.id}`, { data: { active: false } });
  expect(patch.status()).toBe(422);

  await page.goto(`/admin/telecallers?q=${encodeURIComponent(`T25-asha-${stamp}`)}`);
  const row = page.getByRole("row", { name: new RegExp(asha.full_name) });
  await row.getByRole("button", { name: `Deactivate ${asha.full_name}` }).click();
  const group = page.getByRole("group", { name: `Deactivate ${asha.full_name}` });
  await expect(group.getByText("Open work: 1 open lead.")).toBeVisible();
  const confirm = group.getByRole("button", { name: "Confirm deactivate" });
  await expect(confirm).toBeDisabled(); // AC3: a choice is required
  await group.getByRole("radio", { name: "Another IT telecaller" }).check();
  await group.getByRole("combobox", { name: "Hand the leads to" }).fill(`ravi ${stamp}`);
  await group.getByRole("option", { name: new RegExp(ravi.full_name) }).click();
  await confirm.click();
  await expect(page.getByRole("status").filter({ hasText: `Deactivated ${asha.full_name}. 1 open lead now with ${ravi.full_name}.` })).toBeVisible();
  await expect(row.getByText("Inactive")).toBeVisible();
  // AC1: the lead is Ravi's now.
  const ravis = await (await page.request.get(`/api/v1/telecaller/leads/assigned?telecaller_user_id=${ravi.id}`)).json();
  expect(ravis.items.map((x: { id: string }) => x.id)).toContain(enquiry.id);
  await row.getByRole("button", { name: `Reassign ${asha.full_name}'s open leads` }).click();
  await expect(page.getByText(`${asha.full_name} has no open leads.`)).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  await expect(page.getByRole("region", { name: "Telecaller managers" })).toBeVisible();
  expect(errors).toEqual([]);

  // D4 (the card's UI is covered by its component tests; the shared stack holds many managers, so the card's page is not stable):
  // the manager still has Ravi (and inactive Asha) -> a replacement is required, then both move.
  const listed = await (await page.request.get(`/api/v1/admin/telecaller-managers?q=${encodeURIComponent(manager.email)}`)).json();
  expect(listed.items[0].telecaller_count).toBe(2);
  expect((await page.request.post(`/api/v1/admin/telecaller-managers/${manager.id}/deactivate`, { data: {} })).status()).toBe(422);
  const done = await page.request.post(`/api/v1/admin/telecaller-managers/${manager.id}/deactivate`, { data: { reassign_to: spare.id } });
  expect(await done.json()).toEqual({ id: manager.id, active: false, moved_telecallers: 2 });
});
