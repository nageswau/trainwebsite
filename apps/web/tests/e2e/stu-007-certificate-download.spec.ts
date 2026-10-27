import { test, expect } from "@playwright/test";

// STU-007 -- Certificate download. Requires the stack running via `docker compose up`
// with `python -m app.seed` already applied (seeds the demo trainer/student and their
// shared batch enrolment; the demo student is not naturally certificate-eligible, so
// this issues one for real first: since nehn-031 the coordinator issues it, with an override reason).

test("coordinator issues a certificate and the student downloads it via a real signed link (STU-007-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  const context = await (await page.request.get("/api/v1/workflows/it/trainer/context")).json();
  const enrollment = context.enrollments.find((e: { student: string }) => e.student === "Arjun Rao");
  expect(enrollment).toBeTruthy();

  const login = await page.request.post("/api/v1/auth/login", { data: { email: "coordinator@edusphere.local", password: "Demo@123", division: "it" } });
  expect(login.ok()).toBeTruthy();
  const issue = await page.request.post(`/api/v1/workflows/it/certificates/${enrollment.id}/issue`, { data: { override: true, override_reason: "STU-007 e2e" } });
  expect([201, 409]).toContain(issue.status()); // 409: issued by an earlier run on this database

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/certificates");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Certificates" }) });
  // Chromium opens a PDF `window.open` target as a native download rather than a normal
  // page navigation, so assert on the resulting request hitting the real signed-download
  // proxy route instead of a popup page's `url()` (which the PDF viewer never populates).
  const [downloadRequest] = await Promise.all([
    page.context().waitForEvent("request", (req) => req.url().includes("/api/v1/files/signed/")),
    card.getByRole("button", { name: "Download certificate" }).first().click(),
  ]);
  const response = await downloadRequest.response();
  expect(response?.status()).toBe(200);
});

test("certificate download requires authentication", async ({ page, request }) => {
  const response = await request.get("/api/v1/workflows/it/certificates/00000000-0000-0000-0000-000000000000/download");
  expect(response.status()).toBe(401);
});
