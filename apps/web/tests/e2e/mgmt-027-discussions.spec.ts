import { expect, test, type Page } from "@playwright/test";

import { createAndActivate, E2E_PASSWORD } from "./helpers/welcome";

// mgmt-027 (EVID-017 §27, spec MD1-MD14): AC1 -- a partner records the Japan example; AC2 -- the responsible person (a partnership
// head, standing in for the "University BDM") sees "Proceed with agreement — <deadline> — In Progress" and updates it; AC3 -- they never see the
// topic or the discussion points. The responsible person is created through the admin API so the test owns every row it checks.

const PASSWORD = "Demo@123";

async function signIn(page: Page, portal: "admin", email: string, password = PASSWORD) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("signed out, /management/discussions sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/discussions");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fdiscussions$/);
});

test("a partner records the Japan example; the University BDM sees only the decision line and completes it", async ({ browser }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const topic = `Japan University Partnership e2e-${stamp}`;
  const decision = `Proceed with agreement e2e-${stamp}`;

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, "admin", "superadmin@edusphere.local");
  const bdm = await createAndActivate(admin.request, "/api/v1/admin/users", {
    role: "partnership_head", division: "global", full_name: `University BDM ${stamp}`, email: `mgmt027-${stamp}@example.local`,
  });

  const partner = await (await browser.newContext()).newPage();
  await signIn(partner, "admin", "partner.one@edusphere.local");
  await partner.goto("/management");
  await partner.getByRole("link", { name: "Discussions & decisions" }).first().click();
  await partner.getByRole("link", { name: "New discussion" }).click();
  await partner.getByLabel("Topic").fill(topic);
  await partner.getByLabel("Discussion points (optional)").fill("Tokyo terms; commission confidential");
  await partner.getByLabel("Decision (optional)").fill(decision);
  await partner.getByLabel("Person responsible (optional)").selectOption({ label: `University BDM ${stamp} (Partnership Head)` });
  await partner.getByLabel("Deadline (optional)").fill("2099-10-10");
  await partner.getByLabel("Status").selectOption("in_progress");
  await partner.getByRole("button", { name: "Save discussion" }).click();
  await expect(partner.getByRole("heading", { level: 2, name: topic })).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await signIn(staff, "admin", bdm.email, E2E_PASSWORD);
  await staff.goto("/account/management-decisions");
  await expect(staff.getByText(`${decision} — 10 Oct 2099 — In Progress`)).toBeVisible();
  await expect(staff.getByText(topic)).toHaveCount(0);
  await expect(staff.getByText("Tokyo terms")).toHaveCount(0);
  await staff.getByLabel(`Status of “${decision}”`).selectOption("completed");
  await staff.getByRole("button", { name: "Update status" }).click();
  await expect(staff.getByText("Status updated.")).toBeVisible();
  await staff.goto("/management/discussions");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
