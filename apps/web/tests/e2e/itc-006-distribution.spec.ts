import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-006 (DEC-SCOPE-337): a telecaller manager adds a source rule, a website enquiry from that source goes straight to the rule's
// telecaller (AC1, AC4), and the IT team's "When no rule matches" setting is switched to the fewest open leads and back. The source
// is unique per team on a shared database, so super_admin first clears any leftover rule for it, and the run deletes its own.
const SOURCE = "exhibition_event";

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

async function setup(page: Page, stamp: number) {
  await superAdmin(page);
  const leftovers = (await (await page.request.get("/api/v1/telecaller/distribution-rules?team=it&kind=source&limit=100")).json()).items;
  for (const rule of leftovers.filter((r: { source: string }) => r.source === SOURCE)) {
    await page.request.delete(`/api/v1/telecaller/distribution-rules/${rule.id}`);
  }
  await page.request.put("/api/v1/telecaller/distribution-strategy/it", { data: { strategy: "round_robin" } });
  const post = async (data: object) => (await page.request.post("/api/v1/admin/users", { data })).json();
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E Src Manager ${stamp}`, email: `itc006-m-${stamp}@example.local` });
  const tel = await post({
    role: "telecaller", full_name: `E2E Src A ${stamp}`, email: `itc006-a-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `SRC-A-${stamp}`, reporting_manager_user_id: manager.id },
  });
  for (const user of [manager, tel]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, tel };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a source rule routes a website enquiry, and the team strategy switches to the fewest open leads", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const { manager, tel } = await setup(page, stamp);

  await signInManager(page, manager.email);
  await page.getByRole("link", { name: "Distribution rules" }).first().click();
  await page.waitForURL("**/telecaller/manager/distribution");

  // The strategy cards: the IT team is this manager's (editable), the Overseas team is read-only.
  const itCard = page.getByRole("region", { name: "IT team" });
  const overseasCard = page.getByRole("region", { name: "Overseas team" });
  await expect(itCard.getByLabel("When no rule matches")).toHaveValue("round_robin");
  await expect(overseasCard.getByLabel("When no rule matches")).toBeDisabled();
  await expect(overseasCard.getByText("Only a manager with telecallers on the Overseas team can change this.")).toBeVisible();

  // AC1: a source rule for this run's telecaller.
  await page.getByLabel("Rule type (required)").selectOption("source");
  await page.getByLabel("Source (required)").selectOption(SOURCE);
  await page.getByLabel("Telecaller (required)").selectOption({ label: `E2E Src A ${stamp}` });
  await page.getByRole("button", { name: "Create rule" }).click();
  await expect(page.getByText("Created Source: Exhibition/Event.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Rules" }).getByText("Source: Exhibition/Event")).toBeVisible();

  // A website enquiry from that source is assigned to the rule's telecaller on arrival.
  const enquiry = await (await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: `E2E Src Lead ${stamp}`, email: `itc006-l-${stamp}@example.com`, subject: "Python", message: "Call me.", source: SOURCE },
  })).json();
  const mine = (await (await page.request.get(`/api/v1/telecaller/leads/assigned?telecaller_user_id=${tel.id}`)).json()).items;
  expect(mine.map((l: { lead_code: string }) => l.lead_code)).toEqual([enquiry.lead_code]);

  // AC2 setting: the IT team switches to the fewest open leads, then back.
  const select = itCard.getByLabel("When no rule matches");
  await select.selectOption("workload");
  await itCard.getByRole("button", { name: "Save IT strategy" }).click();
  await expect(itCard.getByText("Saved. New IT leads that no rule matches go to the telecaller with the fewest open leads.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "IT team" }).getByLabel("When no rule matches")).toHaveValue("workload");
  await page.getByRole("region", { name: "IT team" }).getByLabel("When no rule matches").selectOption("round_robin");
  await page.getByRole("region", { name: "IT team" }).getByRole("button", { name: "Save IT strategy" }).click();
  await expect(page.getByText(/Saved\. New IT leads that no rule matches go to the next telecaller in turn/)).toBeVisible();

  for (const width of [820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page)).toBe(true);
    // QA-02: the short team settings stay above the long rules list on narrow screens
    const [cardTop, listTop] = await Promise.all([page.getByRole("region", { name: "IT team" }), page.getByRole("region", { name: "Rules" })]
      .map(async (l) => (await l.boundingBox())!.y));
    expect(cardTop).toBeLessThan(listTop);
  }

  // Clean up this run's source rule from the list.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Delete Source: Exhibition/Event" }).click();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.getByText("Deleted Source: Exhibition/Event.")).toBeVisible();
  expect(errors).toEqual([]);
});
