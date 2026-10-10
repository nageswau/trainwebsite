import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-018 (AC2, AC6, AC7, AC10): a student applies to a manager's new university; the manager opens University Performance from the menu
// and sees it ranked with one application, opens Student Opportunities (Leads etc. "Not tracked"), and the university page's funnel card;
// a bad period falls back with a note; a counselor is refused; the pages fit a phone. Throwaway accounts via the real admin API.

async function apiLogin(page: Page, email: string, password: string, division: string) {
  await page.request.post("/api/v1/auth/logout");
  const response = await page.request.post("/api/v1/auth/login", { data: { email, password, division } });
  expect(response.ok(), await response.text()).toBe(true);
}

async function setUp(page: Page, stamp: number) {
  await apiLogin(page, "superadmin@edusphere.local", "Demo@123", "global");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc018-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc018-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U18-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Funnel University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await apiLogin(page, "student.overseas@edusphere.local", "Demo@123", "overseas");
  await post("/api/v1/workflows/overseas/applications", { university_id: university.id, intake: "Sep 2027" });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  return { manager, university };
}

async function signIn(page: Page, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test("a manager ranks their universities, reads the funnel and the university card", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { manager, university } = await setUp(page, stamp);
  await signIn(page, manager.email);
  await page.waitForURL("**/partnership/dashboard");

  // AC7: University Performance from the menu -- the manager's university, ranked, with one application this month.
  await page.getByRole("link", { name: "University Performance" }).first().click();
  await expect(page.getByRole("heading", { name: /^Partner performance — / })).toBeVisible();
  const row = page.getByRole("rowheader", { name: university.name }).locator("xpath=..");
  await expect(row).toContainText("1");
  await expect(row.locator("td").nth(5)).toHaveText("1"); // # , Country, Stage, Health (upc-028), Interested, Applications
  await expect(page.getByRole("rowheader", { name: "Total" })).toBeVisible();

  // AC2: Student Opportunities -- the funnel with the untracked steps.
  await page.getByRole("link", { name: "Student Opportunities" }).first().click();
  const funnel = page.getByRole("list", { name: "Student funnel: all your universities" });
  await expect(funnel.getByRole("listitem").filter({ hasText: "Leads" })).toContainText("Not tracked");
  await expect(funnel.getByRole("listitem").filter({ hasText: "Applications" })).toContainText("1");

  // The university page's card, then the same funnel for that university over another period.
  await page.goto(`/partnership/universities/${university.id}`);
  const card = page.getByRole("region", { name: "Student opportunities this month" });
  await expect(card.getByRole("listitem").filter({ hasText: "Applications" })).toContainText("1");
  await card.getByRole("link", { name: "Another period" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^${university.name} — `) })).toBeVisible();
  await page.getByLabel("From").fill("2024-06-01");
  await page.getByLabel("To").fill("2024-06-30");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(new RegExp(`university_id=${university.id}`));
  await expect(page.getByRole("heading", { name: /1 Jun 2024 – 30 Jun 2024/ })).toBeVisible();
  await expect(page.getByRole("list", { name: `Student funnel: ${university.name}` }).getByRole("listitem").filter({ hasText: "Applications" })).toContainText("0");

  // A bad period in the URL falls back to this month with a note.
  await page.goto("/partnership/performance?from=2024-06-30&to=2024-06-01");
  await expect(page.getByText("The period must start on or before its end — showing this month.")).toBeVisible();

  // AC10: phone width -- no page side-scroll (the table scrolls in its own region).
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/partnership/performance");
  await expect(page.getByRole("rowheader", { name: university.name })).toBeAttached();
  expect(await noSideScroll(page)).toBe(true);
  await page.goto("/partnership/opportunities");
  expect(await noSideScroll(page)).toBe(true);
});

test("a counselor is refused (AC6)", async ({ page }) => {
  await signIn(page, "counselor@edusphere.local", "Demo@123");
  await page.waitForURL("**/overseas/counselor/**");
  await page.goto("/partnership/performance");
  await expect(page.getByText("University performance access required")).toBeVisible();
});
