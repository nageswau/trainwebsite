import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-024 (AC2, AC5, AC9): a partnership head opens the Global University Database from the menu and runs the source's "UK + Business +
// Partnership in Progress"; the chips count each partner status and switch to Partner; the URL keeps the search through Refresh and Back;
// a tuition range without a currency is explained. An overseas_admin runs "Japan + Cyber Security + Not Partnered" without any
// commission filter. The page fits a phone. Universities are tagged with a stamp; throwaway accounts via the real admin API.

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
  const country = async (q: string) => (await (await page.request.get(`/api/v1/lookups/countries?q=${encodeURIComponent(q)}&limit=5`)).json()).items[0].id;
  const [uk, japan] = [await country("United Kingdom"), await country("Japan")];
  const university = async (label: string, countryId: string, stage: string | null, course: { title: string; category: string }) => {
    const { university: u } = await post("/api/v1/partnership/universities", { name: `E2E Srch ${label} ${stamp}`, country_id: countryId, city: "City" });
    if (stage) await post(`/api/v1/partnership/universities/${u.id}/stage`, { from_stage: "target_university", to_stage: stage });
    await post(`/api/v1/partnership/universities/${u.id}/courses`, { ...course, level: "PG", duration: "1 year" });
  };
  const business = { title: "MBA", category: "Business" };
  await university("Talking", uk, "meeting_completed", business);
  await university("Prospect", uk, null, business);
  await university("Partner", uk, "active_partner", business);
  await university("Tokyo", japan, "interested", { title: "MSc Cyber Security", category: "Computer Science" });
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc024-h-${stamp}@example.local` });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc024-a-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, admin };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const results = (page: Page) => page.getByRole("region", { name: "Universities found" }).getByRole("row");

test("a head and an overseas admin search the Global University Database by the §25 examples", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, admin } = await setUp(page, stamp);

  // AC9: the §32 menu entry opens the page.
  await signIn(page, "/admin/login", head.email);
  await page.getByRole("link", { name: "Global University Database" }).first().click();
  await expect(page.getByRole("heading", { name: "Global University Database" })).toBeVisible();
  const form = page.getByRole("search", { name: "Search universities" });
  await expect(form.getByLabel("Commission at least (%)")).toBeVisible(); // U2: a commission role

  // AC2: "UK + Business + Partnership in Progress".
  await form.getByLabel("University", { exact: true }).fill(String(stamp));
  await form.getByLabel("Region").selectOption("UK");
  await form.getByLabel("Course").fill("Business");
  await form.getByLabel("Partner status").selectOption("in_progress");
  await form.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(/region=UK&.*course=Business&.*partner_status=in_progress/);
  await expect(results(page)).toHaveCount(2); // header + one university
  await expect(results(page).nth(1)).toContainText(`E2E Srch Talking ${stamp}`);
  await expect(results(page).nth(1)).toContainText("Meeting Completed");
  await expect(page.getByRole("columnheader", { name: "Matching courses" })).toBeVisible();

  // AC7/AC9: chips count every status under the other filters; one click switches to Partner.
  const chips = page.getByRole("navigation", { name: "Partner status" });
  await expect(chips.getByRole("link")).toHaveText(["Any (3)", "Partner (1)", "Partnership in progress (1)", "Target (1)", "Not partnered (2)", "Lost / closed (0)"]);
  await expect(chips.getByRole("link", { name: "Partnership in progress (1)" })).toHaveAttribute("aria-current", "true");
  await chips.getByRole("link", { name: "Partner (1)" }).click();
  await expect(results(page).nth(1)).toContainText(`E2E Srch Partner ${stamp}`);
  await page.reload();
  await expect(results(page).nth(1)).toContainText(`E2E Srch Partner ${stamp}`);
  await page.goBack();
  await expect(results(page).nth(1)).toContainText(`E2E Srch Talking ${stamp}`);

  // SR8: a tuition range needs a currency -- explained, not searched.
  await form.getByLabel("Tuition from").fill("1000");
  await form.getByRole("button", { name: "Search" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Choose a currency for the tuition range.");

  // AC1 + AC5: the overseas admin runs "Japan + Cyber Security + Not Partnered", with no commission filter offered.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(`/partnership/search?q=${stamp}`);
  const adminForm = page.getByRole("search", { name: "Search universities" });
  await expect(adminForm.getByLabel("Commission at least (%)")).toHaveCount(0);
  await adminForm.getByLabel("Country").fill("Japan");
  await adminForm.getByLabel("Course").fill("Cyber Security");
  await adminForm.getByLabel("Partner status").selectOption("not_partnered");
  await adminForm.getByRole("button", { name: "Search" }).click();
  await expect(results(page)).toHaveCount(2);
  await expect(results(page).nth(1)).toContainText(`E2E Srch Tokyo ${stamp}`);

  // AC9: the page fits a phone.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Global University Database" })).toBeVisible();
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
});
