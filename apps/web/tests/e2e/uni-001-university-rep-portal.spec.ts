import { test, expect } from "@playwright/test";

// UNI-001 -- University Representative portal. Two real gaps this feature closed:
// "Reports" 404'd for this role (same bug class as CNS-001's own Leads/Reports fix), and
// no endpoint existed for a Rep to post an admission update visible to the assigned
// Counselor and Student. Creates its own throwaway application (assigned to the demo
// Rep's own seeded university) rather than mutating the shared seeded demo application --
// same "create your own record" principle used throughout this project.

async function createApplicationForDemoRepsUniversity(page: import("@playwright/test").Page) {
  const studentName = `E2E University Rep Student ${Date.now()}`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email: `uni001-e2e-student-${Date.now()}@example.local`, password: "Sup3r-Secret-Pass!", full_name: studentName, division: "overseas", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();

  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const manchester = universities.find((u) => u.name.includes("Manchester"));
  if (!manchester) throw new Error("Seeded University of Manchester not found");

  const created = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: manchester.id } });
  expect(created.ok()).toBeTruthy();
  const applicationId = (await created.json()).id as string;
  return { applicationId, studentName };
}

test("University Rep's Reports page loads with a real aggregate instead of 404ing (UNI-001-AC01)", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "university.rep@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/university/dashboard");

  await page.goto("/overseas/university/reports");
  await expect(page.getByRole("heading", { name: "University Partner Report" })).toBeVisible();
  await expect(page.getByText("Offers extended")).toBeVisible();
});

test("University Rep posts an admission update through the real UI action (UNI-001-AC01/AC02)", async ({ page }) => {
  const { applicationId } = await createApplicationForDemoRepsUniversity(page);

  await page.goto("/overseas/login");
  await page.fill("#login-email", "university.rep@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/university/dashboard");

  await page.goto("/overseas/university/student-communication");
  await expect(page.getByRole("heading", { name: "Post admission update" })).toBeVisible();
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post admission update" }) });
  await card.locator("input[name='application_id']").fill(applicationId);
  await card.locator("textarea[name='message']").fill("Your application has moved to offer review.");
  await card.getByRole("button", { name: "Post admission update" }).click();
  await expect(card.getByText("Update posted to the student and counselor.")).toBeVisible();
});

test("a Rep cannot post an update to another institution's application, even via a direct ID (UNI-001-AC02)", async ({ page }) => {
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email: `uni001-e2e-other-student-${Date.now()}@example.local`, password: "Sup3r-Secret-Pass!", full_name: `E2E Other Institution Student ${Date.now()}`, division: "overseas", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();

  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const other = universities.find((u) => !u.name.includes("Manchester"));
  if (!other) throw new Error("No second seeded university available in this dataset");
  const created = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: other.id } });
  expect(created.ok()).toBeTruthy();
  const applicationId = (await created.json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "university.rep@edusphere.local", password: "Demo@123", division: "overseas" } });
  const response = await page.request.post(`/api/v1/workflows/overseas/university-rep/applications/${applicationId}/updates`, { data: { message: "Should be denied." } });
  expect(response.status()).toBe(403);
});

test("Offer Letters shows a dedicated, filtered view instead of the generic Applications table (tester feedback 2026-09-04)", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "university.rep@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/university/dashboard");

  await page.goto("/overseas/university/offer-letters");
  await expect(page.getByRole("heading", { name: "Offer Letters" })).toBeVisible();
  await expect(page.getByText("Conditional and unconditional offers")).toBeVisible();
});

test("the university rep portal requires authentication", async ({ page }) => {
  await page.goto("/overseas/university/dashboard");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
