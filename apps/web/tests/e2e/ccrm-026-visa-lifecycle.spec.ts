import { test, expect, type Page } from "@playwright/test";

// ccrm-026 (DEC-SCOPE-254) -- Appendix B "Visa application is submitted": the counselor records appointment, submission date and reference
// through the visa status lifecycle, and the student sees the status label. Requires the stack with `python -m app.seed` applied;
// creates its own application and visa case (ccrm-021's pattern), never touching the seeded student's cases.

async function applicationWithCase(page: Page): Promise<{ university: string; caseId: string }> {
  await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;
  await page.request.post("/api/v1/auth/login", { data: { email: "student.overseas@edusphere.local", password: "Demo@123", division: "overseas" } });
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  for (const university of universities) {
    const created = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: university.id, counselor_id: counselorId } });
    if (!created.ok()) continue; // the seeded student already applied there
    const application = await created.json();
    await page.request.post("/api/v1/auth/login", { data: { email: "counselor@edusphere.local", password: "Demo@123", division: "overseas" } });
    // An empty checklist passes the verified-documents gate, so this test needs no documents.
    const visa = await page.request.post("/api/v1/workflows/overseas/visa", { data: { application_id: application.id, checklist: ["E2E no-op"] } });
    expect(visa.ok()).toBeTruthy();
    const caseId = (await visa.json()).id as string;
    await page.request.patch(`/api/v1/workflows/overseas/visa/${caseId}`, { data: { checklist: [] } });
    return { university: university.name, caseId };
  }
  throw new Error("no university left to apply to");
}

async function signIn(page: Page, email: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a counselor records a submitted visa application and the student sees its status", async ({ page }) => {
  const { university, caseId } = await applicationWithCase(page);
  await signIn(page, "counselor@edusphere.local", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/visa");
  const card = page.locator(`.card:has(#visa-${caseId}-visa_status)`); // the case, not the university: other specs apply there too
  await expect(card.locator(".badge")).toHaveText("Not started");

  await card.getByLabel("Next status").selectOption("preparing");
  await card.getByRole("button", { name: "Save visa case" }).click();
  await expect(card.getByText("Visa status set to Preparing.")).toBeVisible();

  await card.getByLabel("Next status").selectOption("appointment_booked");
  await card.getByRole("button", { name: "Save visa case" }).click();
  await expect(card.getByRole("alert")).toContainText("Add the appointment date before marking the appointment booked");
  await card.getByLabel("Appointment date").fill("2026-11-05");
  await card.getByLabel("Appointment place").fill("VFS Chennai");
  await card.getByRole("button", { name: "Save visa case" }).click();
  await expect(card.getByText("Visa status set to Appointment booked.")).toBeVisible();

  await card.getByLabel("Next status").selectOption("submitted");
  await card.getByLabel("Submission date").fill("2026-10-20");
  await card.getByLabel("Visa application reference").fill("GWF-E2E-1");
  await card.getByRole("button", { name: "Save visa case" }).click();
  await expect(card.getByText("Visa status set to Submitted.")).toBeVisible();
  await expect(card.locator(".badge")).toHaveText("Submitted");
  await expect(card).toContainText("Reference: GWF-E2E-1");
  await expect(card).toContainText("Appointment: 2026-11-05, VFS Chennai");

  await signIn(page, "student.overseas@edusphere.local", "/overseas/student/dashboard");
  await page.goto("/overseas/student/visa-status");
  const studentCard = page.locator(".card", { hasText: university }).first();
  await expect(studentCard.locator(".badge")).toHaveText("Submitted");
  await expect(studentCard).toContainText("Appointment: 2026-11-05, VFS Chennai");
});
