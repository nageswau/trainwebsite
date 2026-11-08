import { expect, test, type Page } from "@playwright/test";

// pob-025 (DEC-SCOPE-436; AC1, AC2): the seeded recruiter sets a 90-day guarantee on a requirement (the edit form), a candidate joins ->
// the placement shows "In guarantee" ending 90 days after joining (AC1); a dropout is recorded -> "Replacement owed" and the placement is
// on the Replacements tab (AC2); the requirement is linked, a second hire is accepted on it -> "Replaced", and the replacement hire shows
// "No fee (replacement)" with no invoice draft. The manager reads without the actions; phone width holds. The expiry alert (AC3), the
// edge (a dropout after the guarantee) and scope are covered by test_pob_025_guarantee.py.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

const istToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

async function hire(page: Page, requirementId: string, name: string, mobile: string): Promise<{ offerId: string; placementId: string }> {
  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(mobile);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.locator("#cand-lawful_basis").selectOption("provided_for_placement");
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateId = page.url().split("/").at(-1)?.split("?")[0];
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId, status: "shortlisted" } });
  expect(added.ok()).toBeTruthy();
  const applicationId = (await added.json()).application.id as string;
  expect((await page.request.post(`/api/v1/recruiter/applications/${applicationId}/status`, { data: { status: "selected" } })).ok()).toBeTruthy();
  const offer = await page.request.post(`/api/v1/recruiter/applications/${applicationId}/offer`, { data: { position: "Java Developer", compensation: 600000, currency: "INR" } });
  const offerId = (await offer.json()).offer.id as string;
  const accepted = await page.request.post(`/api/v1/recruiter/offers/${offerId}/status`, { data: { status: "accepted" } });
  expect(accepted.ok()).toBeTruthy();
  return { offerId, placementId: (await accepted.json()).offer.placement_id as string };
}

test("guarantee: requirement days -> join (AC1) -> dropout (AC2) -> linked replacement, no fee; manager reads; mobile", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(page, "it", "placement@edusphere.local");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Pob025 ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", {
    data: { company_id: (await company.json()).company.id, title: `Java Developer ${stamp}`, location: "Pune", vacancies: 3 },
  });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;

  // G1: the requirement's own guarantee, through the edit form
  await page.goto(`/recruiter/requirements/${requirementId}`);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Guarantee (days)").fill("90");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("region", { name: "Commercial terms" }).getByText("90 days")).toBeVisible();

  // AC1: the end date is computed from the joining date
  const first = await hire(page, requirementId, `E2E Guaranteed ${stamp}`, `9${String(stamp).slice(-9)}`);
  const joined = await page.request.put(`/api/v1/recruiter/offers/${first.offerId}/joining`, { data: { joining_status: "joined", actual_joining_date: istToday(), confirmed_by: "HR" } });
  expect(joined.ok()).toBeTruthy();
  await page.goto(`/recruiter/placements/${first.placementId}`);
  const panel = page.getByRole("region", { name: "Replacement guarantee" });
  await expect(panel.getByText("In guarantee")).toBeVisible();
  await expect(panel.getByText("90 days")).toBeVisible();
  await expect(panel.getByText("90", { exact: true })).toBeVisible(); // days left

  // AC2: a dropout inside the guarantee opens a replacement
  await panel.getByRole("button", { name: "Record dropout" }).click();
  await panel.getByRole("button", { name: "Record dropout" }).last().click(); // no reason: the API's 422 lands on the field
  await expect(panel.getByLabel("Why did the candidate leave?")).toHaveAttribute("aria-invalid", "true");
  await panel.getByLabel("Why did the candidate leave?").fill("Left for a higher offer");
  await panel.getByRole("button", { name: "Record dropout" }).last().click();
  await expect(page.getByRole("status").first()).toHaveText("Dropout recorded. A replacement is owed.");
  await expect(panel.getByText("Replacement owed")).toBeVisible();
  await page.goto("/recruiter/placements?view=replacements");
  await expect(page.getByRole("list", { name: "Placements" }).getByRole("link", { name: `E2E Guaranteed ${stamp}` })).toBeVisible();

  // G6/G7: link the requirement; the next accepted offer on it is the replacement, with no fee and no draft
  await page.goto(`/recruiter/placements/${first.placementId}`);
  await panel.getByRole("button", { name: "Link replacement requirement" }).click();
  await panel.getByLabel("Replacement requirement", { exact: true }).selectOption(requirementId);
  await panel.getByRole("button", { name: "Link requirement" }).click();
  await expect(page.getByRole("status").first()).toHaveText("Replacement requirement linked.");
  await expect(panel.getByText("Replacement in progress")).toBeVisible();
  const second = await hire(page, requirementId, `E2E Replacement ${stamp}`, `8${String(stamp).slice(-9)}`);
  await page.goto(`/recruiter/placements/${first.placementId}`);
  await expect(panel.getByText("Replaced", { exact: true })).toBeVisible();
  await panel.getByRole("link", { name: new RegExp(`E2E Replacement ${stamp}`) }).click();
  await page.waitForURL(`**/recruiter/placements/${second.placementId}`);
  await expect(page.getByRole("region", { name: "Replacement guarantee" }).getByText(`E2E Guaranteed ${stamp}`, { exact: false })).toBeVisible();
  await expect(page.getByText("No fee (replacement)")).toBeVisible();

  // the manager reads without the guarantee actions; phone width holds
  await page.context().clearCookies();
  await signIn(page, "admin", "placement.manager@edusphere.local");
  await page.goto(`/recruiter/placements/${first.placementId}`);
  await expect(page.getByRole("region", { name: "Replacement guarantee" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Replacement guarantee" }).getByRole("button")).toHaveCount(0);
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  expect(consoleErrors.filter((e) => !e.includes("status of 422"))).toEqual([]); // the empty-reason submit above is a deliberate 422
});
