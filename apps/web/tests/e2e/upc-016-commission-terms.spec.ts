import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-016 (AC1, AC2, P1, E1): the owning partnership manager records "15% on first-year tuition, payable after visa approval +
// enrolment" on a draft agreement from the university page, switches it to a fixed amount, sees it on the Commercial Terms menu page and
// removes a mistaken second term. An overseas_admin opening the same university sees no commission anywhere and is refused the menu page.
// The pages fit a phone. Throwaway accounts via the real admin API.

const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc016-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc016-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U16-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc016-a-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Commission University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager, admin]) await activateWithToken(page.request, user.development_welcome_token);
  await signIn(page, "/overseas/login", manager.email);
  const { agreement } = await post(`/api/v1/partnership/universities/${university.id}/agreements`, {
    agreement_type: "commission_agreement", start_date: day(-10), expiry_date: day(3 * 365), exclusivity: "non_exclusive",
  });
  return { manager, admin, university, agreement };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("a manager records commission terms; nobody else sees them", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { admin, university, agreement } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;
  const terms = page.getByRole("region", { name: `Commission terms of ${agreement.mou_number} (restricted)` });
  const status = terms.locator("p[role=status]");

  // P1 + AC2: the owning manager adds the term from the agreement card (validation first).
  await page.goto(universityPage);
  await expect(terms.getByText("No commission terms recorded yet.")).toBeVisible();
  await terms.getByRole("button", { name: "Add commission term" }).click();
  const form = terms.getByRole("form", { name: "New commission term" });
  await form.getByLabel("Commission %").fill("120");
  await form.getByRole("button", { name: "Save term" }).click();
  await expect(form.locator(".form-error[role=alert]")).toHaveText("The commission percentage must be between 0 and 100.");
  await form.getByLabel("Commission %").fill("15");
  await form.getByLabel("Currency (required)").selectOption("GBP");
  await form.getByLabel("Commission trigger (required)").selectOption("visa_and_enrolment");
  await form.getByLabel("Conditions").fill("15% of first-year tuition");
  await form.getByLabel("Payment timeline").fill("Within 60 days of the census date");
  await form.getByRole("combobox", { name: "Add a country" }).fill("India");
  await form.getByRole("option", { name: /^India/ }).first().click();
  await form.getByRole("button", { name: "Save term" }).click();
  await expect(status).toHaveText("Commission term added.");
  const first = terms.getByRole("listitem").first();
  await expect(first.getByText("15%", { exact: true })).toBeVisible();
  await expect(first.getByText("GBP · Visa approval + enrolment")).toBeVisible();
  await expect(first.getByText("All programmes · India")).toBeVisible();

  // E1 / CM2: switching to a fixed amount replaces the percentage.
  await terms.getByRole("button", { name: "Edit commission term 1" }).click();
  const edit = terms.getByRole("form", { name: "Edit commission term 1" });
  await edit.getByLabel("Fixed amount").check();
  await edit.getByLabel("Commission amount").fill("1500");
  await edit.getByRole("button", { name: "Save term" }).click();
  await expect(status).toHaveText("Commission term updated.");
  await expect(first.getByText("GBP 1,500", { exact: true })).toBeVisible();

  // CM11: a mistaken second term comes out after a confirmation.
  await terms.getByRole("button", { name: "Add commission term" }).click();
  const second = terms.getByRole("form", { name: "New commission term" });
  await second.getByLabel("Commission %").fill("5");
  await second.getByLabel("Currency (required)").selectOption("GBP");
  await second.getByLabel("Commission trigger (required)").selectOption("enrolment");
  await second.getByRole("button", { name: "Save term" }).click();
  await expect(status).toHaveText("Commission term added.");
  await expect(terms.getByRole("listitem")).toHaveCount(2);
  await terms.getByRole("button", { name: "Remove commission term 2" }).click();
  await terms.getByRole("button", { name: "Yes, remove" }).click();
  await expect(status).toHaveText("Commission term removed.");
  await expect(terms.getByRole("listitem")).toHaveCount(1);

  // CM14: the Commercial Terms menu lists it.
  await page.getByRole("link", { name: "Commercial Terms" }).first().click();
  await expect(page).toHaveURL(/\/partnership\/commercial-terms$/);
  await page.getByLabel("Search").fill(agreement.mou_number);
  await page.getByRole("button", { name: "Apply" }).click();
  const row = page.getByRole("row", { name: new RegExp(university.name) });
  await expect(row).toContainText("GBP 1,500");
  await expect(row).toContainText("Visa approval + enrolment");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(0);
  await page.goto(universityPage);
  expect(await noSideScroll(page)).toBe(0);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC1 + N1: an overseas_admin reads the university but no commission anywhere, and is refused the menu page and the API.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(universityPage);
  await expect(page.getByRole("heading", { name: university.name })).toBeVisible();
  const html = await page.content();
  expect(html).not.toContain("Commission terms");
  expect(html).not.toContain("1,500");
  expect(html).not.toContain("commission_percent");
  expect((await page.request.get(`/api/v1/partnership/agreements/${agreement.id}/commission-terms`)).status()).toBe(403);
  await page.goto("/partnership/commercial-terms");
  await expect(page.getByText("Commission terms access required")).toBeVisible();
});
