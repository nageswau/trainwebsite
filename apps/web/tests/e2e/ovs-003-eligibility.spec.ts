import { test, expect } from "@playwright/test";

// OVS-003 -- Eligibility evaluation. Requires the stack running via `docker compose up`
// with `python -m app.seed` already applied. Creates its own throwaway application
// (pre-assigned to the seeded counselor) via the real API instead of mutating the
// seeded application already on record for the demo student -- same "create your own
// record, never touch shared seed data" principle used throughout this project.

async function createApplicationAssignedToCounselor(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const counselorId = me.id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const alreadyApplied = ((await (await page.request.get("/api/v1/portal/overseas/student/applications")).json()).rows || []) as { university: string }[];
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const target = universities.find((u) => !alreadyApplied.some((a) => a.university === u.name));
  if (!target) throw new Error("No unapplied university available to pick in this seed dataset");

  const created = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: target.id, counselor_id: counselorId } });
  expect(created.ok()).toBeTruthy();
  return { applicationId: (await created.json()).id as string, universityName: target.name };
}

async function loginAsCounselor(page: import("@playwright/test").Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");
}

test("assigned counselor advances an application to the next confirmed stage (OVS-003-AC01)", async ({ page }) => {
  const { universityName } = await createApplicationAssignedToCounselor(page);
  await loginAsCounselor(page);
  await page.goto("/overseas/counselor/applications");

  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: universityName });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Advance stage" }).click();
  await card.getByRole("button", { name: "Advance" }).click();
  await expect(card.getByText(/Application advanced/)).toBeVisible();
});

test("an unsupported exception-path status is rejected at the API layer, not silently accepted (OVS-003-AC02)", async ({ page }) => {
  const { applicationId } = await createApplicationAssignedToCounselor(page);
  await loginAsCounselor(page);

  const response = await page.request.post(`/api/v1/workflows/overseas/applications/${applicationId}/advance`, { data: { to_status: "rejected" } });
  expect(response.status()).toBe(422);
});

test("the evaluation workspace requires authentication", async ({ page }) => {
  await page.goto("/overseas/counselor/applications");
  await expect(page).toHaveURL(/\/overseas\/login/);
});
