import { expect, test, type Page } from "@playwright/test";

// upc-033 (DEC-SCOPE-174 PX6/PX10): the UI as built. Commission is planted on a published university (a course percentage, an agreement
// term, its conditions); the super admin sees it on the university page (positive control). The overseas admin opens the same page and
// the counselor and the public catalogue open theirs: none shows a commission figure, a commission word or the planted text, and the
// commission-only Commercial Terms menu answers "Access unavailable". The counselor is refused the partnership pages. Phone width fits.

const PERCENT = "73.19";
const TERM = "61.83";

async function signIn(page: Page, loginPath: string, email: string, password = "Demo@123") {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

function day(offset: number) {
  return new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local");
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const name = `E2E Confidential University ${stamp}`;
  const { university } = await post(page, "/api/v1/partnership/universities", { name, country_id: countries.items[0].id, city: "Leeds", overview: "A partner." });
  await post(page, `/api/v1/partnership/universities/${university.id}/publish`, {});
  const base = `/api/v1/partnership/universities/${university.id}`;
  await post(page, `${base}/courses`, {
    title: `MSc Confidential ${stamp}`, level: "PG", category: `E2E cat ${stamp}`, duration: "1 year", intakes: ["Sep"],
    tuition_amount: "18000", tuition_currency: "GBP", commission: { percent: PERCENT },
  });
  const { agreement } = await post(page, `${base}/agreements`, {
    agreement_type: "commission_agreement", start_date: day(-10), expiry_date: day(3 * 365), exclusivity: "non_exclusive",
  });
  const conditions = `Zq033secret ${stamp}`;
  await post(page, `/api/v1/partnership/agreements/${agreement.id}/commission-terms`, {
    commission_percent: TERM, currency: "GBP", trigger: "enrolment", conditions,
  });
  return { university, name, conditions };
}

async function expectNoSecrets(page: Page, conditions: string) {
  const text = await page.locator("body").innerText();
  for (const secret of [PERCENT, TERM, conditions]) expect(text).not.toContain(secret);
}

async function expectNoCommission(page: Page, conditions: string) {
  // The word is checked in the page content: overseas_admin's own menu has "Commissions", the agent-commission module (DEC-SCOPE-005, PX8).
  expect(await page.evaluate(() => (document.querySelector("main") ?? document.body).innerText)).not.toMatch(/commission/i);
  await expectNoSecrets(page, conditions);
}

test("commission reaches the commission roles only", async ({ page }) => {
  const stamp = Date.now();
  const { university, name, conditions } = await setUp(page, stamp);

  // Positive control: the super admin (a commission role) sees the planted figures on the university page.
  await page.goto(`/partnership/universities/${university.id}`);
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
  await expect(page.locator("body")).toContainText(`${PERCENT}%`);
  await expect(page.locator("body")).toContainText(conditions);

  // The public catalogue page of the same university.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/overseas/universities/${university.slug}`);
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
  await expectNoCommission(page, conditions);

  // The overseas admin reads the partnership record (U14) without commission, and is refused the commission menu.
  await signIn(page, "/overseas/login", "overseasadmin@edusphere.local");
  await page.goto(`/partnership/universities/${university.id}`);
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
  await expect(page.locator("body")).toContainText(`MSc Confidential ${stamp}`);
  await expectNoCommission(page, conditions);
  await page.goto("/partnership/commercial-terms");
  await expect(page.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeVisible();

  // The counselor's university page shows the course without commission; the partnership pages refuse them.
  await signIn(page, "/overseas/login", "counselor@edusphere.local");
  await page.goto(`/overseas/counselor/universities/${university.id}`);
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
  await expectNoCommission(page, conditions);
  // (The refusal names the area -- "Commission terms access required" -- so only the planted values are checked here.)
  for (const path of [`/partnership/universities/${university.id}`, "/partnership/commercial-terms"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeVisible();
    await expectNoSecrets(page, conditions);
  }

  // Phone width: the overseas admin's university page has no horizontal page scroll.
  await signIn(page, "/overseas/login", "overseasadmin@edusphere.local");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/partnership/universities/${university.id}`);
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
