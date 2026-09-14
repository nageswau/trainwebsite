import { test, expect } from "@playwright/test";

// VISA-001 -- Visa checklist and documentation. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied. Creates its own
// throwaway application (pre-assigned to the seeded counselor) instead of touching the
// seeded student's own on-record application/visa case.

async function createApplicationAssignedToCounselor(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const alreadyApplied = ((await (await page.request.get("/api/v1/portal/overseas/student/applications")).json()).rows || []) as { university: string }[];
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const target = universities.find((u) => !alreadyApplied.some((a) => a.university === u.name));
  if (!target) throw new Error("No unapplied university available to pick in this seed dataset");
  const application = await (await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: target.id, counselor_id: counselorId } })).json();
  return { applicationId: application.id as string, universityName: target.name };
}

async function loginAsCounselor(page: import("@playwright/test").Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");
}

test("counselor starts a visa case with a real checklist, and the student can view it even unverified (VISA-001-AC01/AC02)", async ({ page }) => {
  const { universityName } = await createApplicationAssignedToCounselor(page);

  await loginAsCounselor(page);
  await page.goto("/overseas/counselor/visa");
  const counselorCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Cases" }) }).locator(".card", { hasText: universityName });
  await expect(counselorCard).toBeVisible();
  await counselorCard.getByLabel("Checklist items (comma separated)").fill("Passport, Offer letter");
  await counselorCard.getByRole("button", { name: "Start visa case" }).click();
  await expect(counselorCard.getByText("Visa case started.")).toBeVisible();
  await expect(counselorCard.getByText("Passport")).toBeVisible();

  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");

  await page.goto("/overseas/student/visa-status");
  const studentCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Checklist" }) }).locator(".card", { hasText: universityName });
  await expect(studentCard).toBeVisible();
  await expect(studentCard.getByText("Passport")).toBeVisible();
  await expect(studentCard.getByText(/not uploaded/).first()).toBeVisible();
});

test("advancing past the checklist stage is blocked while a document is unverified, not silently accepted (VISA-001-AC02)", async ({ page }) => {
  const { applicationId, universityName } = await createApplicationAssignedToCounselor(page);
  // `createApplicationAssignedToCounselor` leaves the session logged in as the student
  // (its last internal step) -- re-authenticate as the counselor before this
  // counselor-only write, otherwise it 403s silently.
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const created = await page.request.post("/api/v1/workflows/overseas/visa", { data: { application_id: applicationId, checklist: ["Passport"] } });
  expect(created.ok()).toBeTruthy();

  await loginAsCounselor(page);
  await page.goto("/overseas/counselor/visa");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Cases" }) }).locator(".card", { hasText: universityName });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Advance to Documentation" }).click();
  await expect(card.getByText(/Cannot advance past the checklist stage/)).toBeVisible();
});

test("the visa workspaces require authentication", async ({ page }) => {
  await page.goto("/overseas/student/visa-status");
  await expect(page).toHaveURL(/\/overseas\/login/);
  await page.goto("/overseas/counselor/visa");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
