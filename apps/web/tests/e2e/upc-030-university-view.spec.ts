import { expect, test, type Page } from "@playwright/test";

// upc-030 (DEC-SCOPE-161, AC8): one university record, a slice per role. The seeded counselor finds a published university from the
// Universities nav and checks its IELTS requirement (the backlog's positive scenario) with no commission or internal contact on the page;
// the seeded university rep opens their own University Profile; a BDM sees the profile, stage and manager only. Phone width holds.

async function signIn(page: Page, loginPath: string, email: string, password = "Demo@123") {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const name = `E2E View University ${stamp}`;
  const { university } = await post("/api/v1/partnership/universities", { name, country_id: countries.items[0].id, city: "Leeds", overview: "A research university.", website: "https://view.example.ac.uk" });
  await post(`/api/v1/partnership/universities/${university.id}/courses`, {
    title: "MSc Data Science", level: "PG", category: "Computing", duration: "1 year", tuition_amount: "21000", tuition_currency: "GBP", intakes: ["Sep"],
    entry_requirements: "A 2:1 honours degree", english_test: "IELTS", english_score: "6.5", commission: { percent: "12.5" },
  });
  await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "Asha Admissions", email: "asha@view.example.ac.uk", shareable: true });
  await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "Victor Internal", email: "victor@view.example.ac.uk", notes: "Prefers mornings" });
  await post(`/api/v1/partnership/universities/${university.id}/publish`, {});
  await page.request.post("/api/v1/auth/logout");
  return { university, name };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("a counselor checks a partner university's IELTS requirement; the rep and a BDM see only their slices", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { university, name } = await setUp(page, stamp);

  // Counselor: nav → search → the 360 view.
  await signIn(page, "/overseas/login", "counselor@edusphere.local");
  await page.getByRole("link", { name: "Universities", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Partner universities" })).toBeVisible();
  await page.getByLabel("Search by name or city").fill(name);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  const courses = page.getByRole("region", { name: "Courses" });
  await expect(courses.getByText("IELTS 6.5")).toBeVisible();
  await expect(courses.getByText("A 2:1 honours degree")).toBeVisible();
  await expect(page.getByRole("region", { name: "Application contacts" })).toContainText("Asha Admissions");
  await expect(page.locator("body")).not.toContainText("Victor Internal");
  await expect(page.locator("body")).not.toContainText(/commission/i);
  await expect(page.getByRole("region", { name: "Your students' applications" })).toContainText("No applications for this university yet.");
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1366, height: 900 });

  // Counselor: an unknown university is refused without leaking anything.
  await page.goto("/overseas/counselor/universities/00000000-0000-0000-0000-000000000000");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("University not found")).toBeVisible();

  // University rep: their own university's profile and courses only.
  await signIn(page, "/overseas/login", "university.rep@edusphere.local");
  await page.getByRole("link", { name: "University Profile" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "University of Manchester" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Courses" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Application contacts" })).toHaveCount(0);
  await page.goto(`/overseas/counselor/universities/${university.id}`);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  // BDM: profile, stage and manager only.
  await signIn(page, "/overseas/login", "bdm.agent@edusphere.local");
  await page.goto(`/bdm/universities/${university.id}`);
  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  await expect(page.getByRole("region", { name: "Partnership" })).toContainText("Not assigned yet");
  await expect(page.getByRole("region", { name: "Courses" })).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(/commission/i);
});
