import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-007 (AC5, AC7, DI3, DI4): a telecaller manager keeps a city rule for their telecallers, a website enquiry is distributed on
// arrival, and leads are reassigned from the Lead assignment page. The database is shared, so round robin may pick any active IT
// telecaller: super_admin first moves the new lead onto this run's team, then the manager reassigns it inside their reports.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signInManager(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/telecaller/manager/team");
}

async function accounts(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (data: object) => (await page.request.post("/api/v1/admin/users", { data })).json();
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E Dist Manager ${stamp}`, email: `tel007-m-${stamp}@example.local` });
  const telecaller = (n: string) => post({
    role: "telecaller", full_name: `E2E Dist ${n} ${stamp}`, email: `tel007-${n.toLowerCase()}-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `DS-${n}-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const [a, b] = [await telecaller("A"), await telecaller("B")];
  const other = await post({ role: "telecaller_manager", division: "global", full_name: `E2E Dist Other ${stamp}`, email: `tel007-o-${stamp}@example.local` });
  const stranger = await post({
    role: "telecaller", full_name: `E2E Dist Stranger ${stamp}`, email: `tel007-s-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `DS-S-${stamp}`, reporting_manager_user_id: other.id },
  });
  for (const user of [manager, a, b]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, a, b, stranger };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("rules, distribution on intake and reassignment from the Lead assignment page", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const { manager, a, b, stranger } = await accounts(page, stamp);
  const town = `E2E Town ${stamp}`;

  // A website enquiry is distributed in its own transaction (DI2): it comes back Assigned.
  const enquiry = await (await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: `E2E Dist Lead ${stamp}`, email: `tel007-l-${stamp}@example.com`, subject: "Cyber security", message: "Please call me." },
  })).json();
  expect(enquiry.status).toBe("assigned");

  // super_admin moves it onto this run's telecaller A from the Assigned tab.
  await page.goto("/telecaller/manager/assignment?view=assigned");
  await page.getByRole("searchbox", { name: "Search leads" }).fill(enquiry.lead_code);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(new RegExp(`q=${enquiry.lead_code}`));
  await expect(page.getByRole("region", { name: "Leads" }).locator("tbody tr")).toHaveCount(1); // the searched list, not the one before it
  await page.getByRole("checkbox", { name: `Select E2E Dist Lead ${stamp}` }).check();
  await page.getByLabel("Assign to").selectOption({ label: `E2E Dist A ${stamp} (IT)` });
  await page.getByRole("button", { name: "Reassign 1 selected" }).click();
  await expect(page.getByText(new RegExp(`Reassigned 1 lead to E2E Dist A ${stamp}|1 already with them`))).toBeVisible();

  // The manager: a city rule for A, changed to B, then deleted (DI3, D6).
  await signInManager(page, manager.email);
  await page.getByRole("link", { name: "Distribution rules" }).first().click();
  await page.waitForURL("**/telecaller/manager/distribution");
  await page.getByLabel("Rule type (required)").selectOption("city");
  await page.getByLabel("City (required)").fill(town);
  await page.getByLabel("Telecaller (required)").selectOption({ label: `E2E Dist A ${stamp}` });
  await page.getByRole("button", { name: "Create rule" }).click();
  await expect(page.getByText(`Created City: ${town}.`)).toBeVisible();
  await page.getByRole("button", { name: `Change telecaller for City: ${town}` }).click();
  await page.getByLabel(`New telecaller for City: ${town}`).selectOption({ label: `E2E Dist B ${stamp}` });
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`City: ${town} now goes to E2E Dist B ${stamp}.`)).toBeVisible();
  await page.getByRole("button", { name: `Delete City: ${town}` }).click();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.getByText(`Deleted City: ${town}.`)).toBeVisible();

  // Lead assignment: the queue renders; the team's tab shows A's lead; reassigning to B keeps its stage.
  await page.getByRole("link", { name: "Lead assignment" }).first().click();
  await page.waitForURL("**/telecaller/manager/assignment");
  await expect(page.getByRole("tab", { name: "Unassigned" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Assigned to my team" }).click();
  await page.getByLabel("Telecaller", { exact: true }).selectOption({ label: `E2E Dist A ${stamp}` });
  await expect(page).toHaveURL(new RegExp(`telecaller=${a.id}`));
  await expect(page.getByRole("region", { name: "Leads" }).locator("tbody tr")).toHaveCount(1);
  await expect(page.getByRole("cell", { name: `E2E Dist Lead ${stamp}`, exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: `Select E2E Dist Lead ${stamp}` }).check();
  await page.getByLabel("Assign to").selectOption({ label: `E2E Dist B ${stamp} (IT)` });
  await page.getByRole("button", { name: "Reassign 1 selected" }).click();
  await expect(page.getByText(`Reassigned 1 lead to E2E Dist B ${stamp}.`)).toBeVisible();
  const row = (await (await page.request.get(`/api/v1/telecaller/leads/assigned?telecaller_user_id=${b.id}`)).json()).items[0];
  expect([row.lead_code, row.status]).toEqual([enquiry.lead_code, "assigned"]);

  expect((await (await page.request.get(`/api/v1/telecaller/leads/assigned?telecaller_user_id=${a.id}`)).json()).total).toBe(0);

  // AC5: a telecaller outside my reports is refused, and their leads are not mine to list.
  const refused = await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: [enquiry.id], telecaller_user_id: stranger.id } });
  expect([refused.status(), (await refused.json()).detail]).toEqual([403, "You can only assign leads to your direct reports"]);
  expect((await page.request.get(`/api/v1/telecaller/leads/assigned?telecaller_user_id=${stranger.id}`)).status()).toBe(404);

  for (const width of [820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page)).toBe(true);
  }
  expect(errors).toEqual([]);
});
