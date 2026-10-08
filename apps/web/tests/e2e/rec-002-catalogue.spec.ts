import { expect, test, type Page } from "@playwright/test";

// rec-002 (AC1-AC6): the placement manager keeps the recruiter lists -- seeds in source order, add, duplicate refused, rename,
// deactivate (gone from a recruiter's picker read, kept for the manager), campaigns; a recruiter reads but cannot write.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const LEAD_SOURCES = "/api/v1/recruiter/catalogue/lead-sources";

test("placement manager keeps the lists; a recruiter reads active values only", async ({ page }) => {
  test.setTimeout(60_000);
  const stamp = Date.now();
  const naukri = `Naukri ${stamp}`;
  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.getByRole("link", { name: "Catalogues" }).first().click();
  await page.waitForURL("**/recruiter/manager/catalogue/lead-sources");
  await expect(page.getByRole("heading", { name: "Lead sources", level: 2 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Lead sources" })).toHaveAttribute("aria-current", "page");
  const table = page.getByRole("region", { name: "Lead sources" });
  await expect(table.getByRole("cell", { name: "LinkedIn", exact: true })).toBeVisible();
  await expect(table.getByRole("cell", { name: "WhatsApp campaigns", exact: true })).toBeVisible();

  // AC4: add, then the same name in another case is refused.
  await page.getByLabel("Lead source name (required)").fill(naukri);
  await page.getByRole("button", { name: "Add lead source" }).click();
  await expect(page.getByText(`Added ${naukri}.`)).toBeVisible();
  await expect(table.getByRole("cell", { name: naukri, exact: true })).toBeVisible();
  await page.getByLabel("Lead source name (required)").fill(naukri.toUpperCase());
  await page.getByRole("button", { name: "Add lead source" }).click();
  await expect(page.getByText(`A value named “${naukri.toUpperCase()}” already exists in this list`)).toBeVisible();

  // AC5 + AC2: rename keeps the row; deactivate after a confirm.
  const renamed = `${naukri} Jobs`;
  await page.getByRole("button", { name: `Edit ${naukri}` }).click();
  await page.locator("input[name=name][id^=rec-value-name-]").fill(renamed);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`Saved ${renamed}.`)).toBeVisible();
  await page.getByRole("button", { name: `Deactivate ${renamed}` }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByText(`Deactivated ${renamed}.`)).toBeVisible();
  await expect(page.getByRole("button", { name: `Reactivate ${renamed}` })).toBeVisible();

  // Industries start empty (C1); company sizes are the owner's bands (C2).
  await page.getByRole("link", { name: "Company sizes" }).click();
  await expect(page.getByRole("region", { name: "Company sizes" }).getByRole("cell", { name: "1001+", exact: true })).toBeVisible();

  // AC6: a campaign under an active lead source.
  await page.getByRole("link", { name: "Campaigns" }).click();
  await page.waitForURL("**/catalogue/campaigns");
  const campaign = `Q4 IT hiring push ${stamp}`;
  await page.getByLabel("Campaign name (required)").fill(campaign);
  await page.getByLabel("Lead source (required)").selectOption({ label: "LinkedIn" });
  await expect(page.getByLabel("Lead source (required)").locator("option", { hasText: renamed })).toHaveCount(0); // deactivated: not offered
  await page.getByLabel("Start date (required)").fill("2026-10-01");
  await page.getByLabel("End date").fill("2026-09-01");
  await page.getByRole("button", { name: "Create campaign" }).click();
  await expect(page.getByText("End date cannot be before the start date")).toBeVisible();
  await page.getByLabel("End date").fill("2026-12-31");
  await page.getByRole("button", { name: "Create campaign" }).click();
  await expect(page.getByText(`Created ${campaign}.`)).toBeVisible();
  await expect(page.getByRole("region", { name: "Campaigns" }).getByRole("cell", { name: campaign, exact: true })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // AC2 + AC3: the recruiter's read omits the deactivated value; writes and the manager page are refused.
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  const read = await page.request.get(`${LEAD_SOURCES}?q=${encodeURIComponent(naukri)}`);
  expect(read.status()).toBe(200);
  expect((await read.json()).items).toEqual([]);
  expect((await page.request.post(LEAD_SOURCES, { data: { name: `Recruiter ${stamp}` } })).status()).toBe(403);
  await page.goto("/recruiter/manager/catalogue/lead-sources");
  await expect(page.getByText("Placement manager role required")).toBeVisible();
});

test("an unknown catalogue tab is a 404 and the index opens the first tab", async ({ page }) => {
  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.goto("/recruiter/manager/catalogue");
  await page.waitForURL("**/recruiter/manager/catalogue/lead-sources");
  const missing = await page.goto("/recruiter/manager/catalogue/colours");
  expect(missing?.status()).toBe(404);
});
