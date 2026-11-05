import { expect, test, type Page } from "@playwright/test";

// hrc-021 (DEC-SCOPE-397): the derived engagement status. The seeded recruiter adds a candidate (they become its owner, hrc-012 O7), so
// the list shows Uncontacted and the Engagement filter finds it; after a logged call the detail and the list say Contacted; setting the
// stored status to Do not contact (a manual flag) overrides it. The list's Engagement filter survives a refresh and fits a phone.

const RECRUITER = "placement@edusphere.local";

async function signIn(page: Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", RECRUITER);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
}

test("engagement: uncontacted on add, contacted after a call, a manual flag overrides; list filter", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Engage ${Date.now()}`;
  await signIn(page);
  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(`9${String(Date.now()).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.locator("#cand-lawful_basis").selectOption("provided_for_placement"); // hrc-035 K1
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const detailUrl = page.url();
  await expect(page.getByText("Engagement: Uncontacted")).toBeVisible();

  // The list: the chip, and the filter (in the URL, so a refresh keeps it).
  await page.goto(`/recruiter/candidates?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText("Uncontacted");
  await page.getByLabel("Engagement").selectOption("contacted");
  await expect(page).toHaveURL(/engagement=contacted/);
  await expect(page.getByText("No candidates match these filters.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Engagement")).toHaveValue("contacted");

  // A logged call makes them Contacted.
  await page.goto(detailUrl);
  const calls = page.getByRole("region", { name: "Calls" });
  await calls.getByRole("button", { name: "Log call" }).click();
  const form = calls.getByRole("form", { name: "Log call" });
  await form.getByLabel("Outcome (required)").selectOption("no_answer");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(calls.getByText("Call logged.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Engagement: Contacted")).toBeVisible();
  await page.goto(`/recruiter/candidates?q=${encodeURIComponent(name)}&engagement=contacted`);
  await expect(page.getByRole("link", { name })).toBeVisible();

  // AC2: the manual flag (stored status Do not contact) overrides the derived value.
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "Edit" }).click();
  await page.locator("#cand-status").selectOption("do_not_contact");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Engagement: Do not contact")).toBeVisible();

  // The filter row and the column fit a phone without the page scrolling sideways.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/recruiter/candidates?q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText("Do not contact");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
