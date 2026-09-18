import { test, expect } from "@playwright/test";

// VISA-003 -- Visa approval status tracking. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied. Creates its own
// throwaway application (pre-assigned to the seeded counselor) instead of touching the
// seeded student's own on-record application/visa case.

async function createVisaCaseAssignedToCounselor(page: import("@playwright/test").Page, trackingReference: string) {
  // The seeded university list is finite and the shared demo student accumulates
  // applications against it across repeated runs -- create a fresh, guaranteed-unapplied
  // university as an admin first instead of hunting for one (same fix already applied in
  // visa-002-interview-prep.spec.ts for the identical root cause).
  const unique = `visa003-${Date.now()}`;
  const universityName = `VISA-003 Test University ${unique}`;
  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const university = await (await page.request.post("/api/v1/admin/universities", { data: { country_slug: "usa", slug: unique, name: universityName } })).json();

  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const application = await (await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: university.id, counselor_id: counselorId } })).json();

  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const created = await page.request.post("/api/v1/workflows/overseas/visa", { data: { application_id: application.id, checklist: ["Passport"], tracking_reference: trackingReference } });
  expect(created.ok()).toBeTruthy();

  return { universityName };
}

test("student sees the visa status tracking reference and the compliance disclaimer (VISA-003-AC01/AC02)", async ({ page }) => {
  const trackingReference = `TRK-${Date.now()}`;
  const { universityName } = await createVisaCaseAssignedToCounselor(page, trackingReference);

  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");

  await page.goto("/overseas/student/visa-status");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Checklist" }) }).locator(".card", { hasText: universityName });
  await expect(card).toBeVisible();
  await expect(card.getByText(trackingReference)).toBeVisible();
  await expect(page.getByText("EduSphere does not decide visa outcomes")).toBeVisible();
});

test("counselor sees the same tracking reference and compliance disclaimer (VISA-003-AC01/AC02)", async ({ page }) => {
  const trackingReference = `TRK-${Date.now()}`;
  const { universityName } = await createVisaCaseAssignedToCounselor(page, trackingReference);

  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");

  await page.goto("/overseas/counselor/visa");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visa Cases" }) }).locator(".card", { hasText: universityName });
  await expect(card).toBeVisible();
  await expect(card.getByText(trackingReference)).toBeVisible();
  await expect(page.getByText("EduSphere does not decide visa outcomes")).toBeVisible();
});
