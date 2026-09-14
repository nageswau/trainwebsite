import { test, expect } from "@playwright/test";

// OVS-004 -- Application status tracking and notifications. Requires the stack running
// via `docker compose up` with `python -m app.seed` already applied. Creates its own
// throwaway application (pre-assigned to the seeded counselor) instead of touching the
// seeded student's own on-record application.

test("student views their application's status history after a counselor advances it (OVS-004-AC01)", async ({ page }) => {
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;

  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const alreadyApplied = ((await (await page.request.get("/api/v1/portal/overseas/student/applications")).json()).rows || []) as { university: string }[];
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const target = universities.find((u) => !alreadyApplied.some((a) => a.university === u.name));
  if (!target) throw new Error("No unapplied university available to pick in this seed dataset");
  const application = await (await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: target.id, counselor_id: counselorId } })).json();

  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  await page.request.post(`/api/v1/workflows/overseas/applications/${application.id}/advance`, { data: { to_status: "eligibility_evaluation" } });

  await page.goto("/overseas/login");
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/dashboard");

  await page.goto("/overseas/student/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a University" }) }).locator(".card", { hasText: target.name });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "View status history" }).click();
  await expect(card.getByText("eligibility evaluation")).toBeVisible();
});
