import { expect, test, type Page } from "@playwright/test";

// mgmt-024 (§20, spec MF1-MF18, M9/M13): the partner opens the Applications funnel from the Command Center, sees the eleven stages (three
// "Not tracked") and narrows it with the URL-held filters; the super admin sees it too; the accountant is refused. Seeded demo accounts.
// The shared stack DB also holds backend-test rows, so the checks are relational (a filter never raises a count), not fixed numbers.

const LABELS = [
  "Applications Created", "Documents Complete", "Submitted", "Under Review", "Offer", "Accepted", "Deposit", "CAS/COE", "Visa", "Visa Approved",
  "Enrollment",
]; // prettier-ignore

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const rows = (page: Page) => page.getByRole("list", { name: "Application funnel" }).getByRole("listitem");

async function created(page: Page): Promise<number> {
  return Number((await rows(page).first().locator(".funnel-count").textContent())!.replaceAll(",", ""));
}

test("a partner opens the funnel from the Command Center and narrows it by status", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "Students" }).getByRole("link", { name: "Applications" }).click();
  await page.waitForURL("**/management/applications");
  await expect(page.getByRole("heading", { level: 2, name: "Applications funnel" })).toBeVisible();
  await expect(rows(page).locator(".funnel-label")).toHaveText(LABELS);
  for (const index of [3, 5, 7]) await expect(rows(page).nth(index)).toContainText("Not tracked");
  const all = await created(page);

  const form = page.getByRole("form", { name: "Application filters" });
  await form.getByLabel("Status").selectOption("enquiry");
  await form.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(/\/management\/applications\?status=enquiry$/); // QA24-01: the empty fields are dropped
  expect(await created(page)).toBeLessThanOrEqual(all);
  await expect(form.getByLabel("Status")).toHaveValue("enquiry");

  await page.reload(); // the filter lives in the address
  await expect(page.getByRole("form", { name: "Application filters" }).getByLabel("Status")).toHaveValue("enquiry");
  await page.getByRole("link", { name: "Clear filters" }).click();
  await page.waitForURL(/\/management\/applications$/);
  expect(await created(page)).toBe(all);
});

test("the super admin sees the funnel too (operational tier)", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.goto("/management/applications");
  await expect(rows(page)).toHaveCount(11);
});

test("the accountant has no entry, and a direct visit is refused", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await expect(page.getByRole("link", { name: "Applications", exact: true })).toHaveCount(0);
  expect((await page.request.get("/api/v1/management/applications")).status()).toBe(403);
  await page.goto("/management/applications");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});

test("an end date before the start date shows the API's message", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.goto("/management/applications?date_from=2026-05-01&date_to=2026-04-01");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The end date must be on or after the start date"); // not Next's route announcer
});

test("signed out, the funnel sends you to the admin sign-in", async ({ page }) => {
  await page.goto("/management/applications");
  await expect(page).toHaveURL(/\/admin\/login\?next=%2Fmanagement%2Fapplications$/);
});
