import { test, expect } from "@playwright/test";

// VISA-002 -- Visa interview preparation. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds
// Country.interview_prep for "usa"/"united-kingdom" only -- every other seeded country
// has none, deliberately, so the fallback path is real). Creates its own throwaway
// application per test instead of touching the seeded student's own on-record
// application/visa case.

async function createApplicationForCountry(page: import("@playwright/test").Page, countrySlug: string) {
  // Seeded countries only have 1-2 universities each, and the shared demo student has
  // accumulated applications against most of them over a long session -- rather than
  // hunting for a still-unapplied one (which can legitimately run out), create a fresh,
  // guaranteed-unapplied university under the target country as an admin first.
  const unique = `${countrySlug}-visa002-${Date.now()}`;
  const universityName = `VISA-002 Test University ${unique}`;
  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const university = await (await page.request.post("/api/v1/admin/universities", { data: { country_slug: countrySlug, slug: unique, name: universityName } })).json();

  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const application = await (await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: university.id, counselor_id: counselorId } })).json();

  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const created = await page.request.post("/api/v1/workflows/overseas/visa", { data: { application_id: application.id, checklist: ["Passport"] } });
  expect(created.ok()).toBeTruthy();

  return { universityName };
}

async function loginAsStudent(page: import("@playwright/test").Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");
}

test("student sees real interview prep material for a country that has it (VISA-002-AC01)", async ({ page }) => {
  const { universityName } = await createApplicationForCountry(page, "usa");

  await loginAsStudent(page);
  await page.goto("/overseas/student/visa-status");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Checklist" }) }).locator(".card", { hasText: universityName });
  await expect(card).toBeVisible();
  await expect(card.getByText("Interview preparation")).toBeVisible();
  await expect(card.getByText(/I-20/)).toBeVisible();
});

test("student sees an honest fallback, not a broken page, for a country with no prep material yet (VISA-002-AC02)", async ({ page }) => {
  const { universityName } = await createApplicationForCountry(page, "germany");

  await loginAsStudent(page);
  await page.goto("/overseas/student/visa-status");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Checklist" }) }).locator(".card", { hasText: universityName });
  await expect(card).toBeVisible();
  await expect(card.getByText(/has not been published for Germany yet/)).toBeVisible();
});

test("the visa workspace requires authentication", async ({ page }) => {
  await page.goto("/overseas/student/visa-status");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
