import { test, expect } from "@playwright/test";

// EMP-005 -- Interview list and status. The list itself and its RBAC scoping already
// existed (built for EMP-004); the real gap was the UI never displaying an interview's
// result/status at all, so a cancelled interview -- while still present in the data --
// was indistinguishable from any other. Confirms the interview card now shows an honest
// status, both before and after Placement Team records an outcome.

async function registerEmployer(page: import("@playwright/test").Page) {
  const unique = Date.now();
  const email = `emp005-e2e-${unique}@example.local`;
  const response = await page.request.post("/api/v1/employer/register", {
    data: {
      email,
      password: "Sup3r-Secret-Pass!",
      full_name: "E2E Employer",
      company_name: `E2E Hiring ${unique}`,
      company_website: "https://example.com",
    },
  });
  expect(response.ok()).toBeTruthy();
  return { email };
}

async function loginAsEmployer(page: import("@playwright/test").Page, email: string) {
  const response = await page.request.post("/api/v1/auth/login", { data: { email, password: "Sup3r-Secret-Pass!", division: "it" } });
  expect(response.ok()).toBeTruthy();
}

async function ensureSeededStudentIsAnAvailableCandidate(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "student.it@edusphere.local", password: "Demo@123", division: "it" } });
  const student = await (await page.request.get("/api/v1/auth/me")).json();
  await page.request.post("/api/v1/auth/login", { data: { email: "itadmin@edusphere.local", password: "Demo@123", division: "it" } });
  await page.request.put(`/api/v1/workflows/it/placement/profiles/${student.id}`, { data: { available: true, withdrawn: false } });
  return { name: student.full_name as string };
}

test("Employer's interview list shows an honest status before and after Placement Team records an outcome (EMP-005-AC01/AC02)", async ({ page }) => {
  const { name } = await ensureSeededStudentIsAnAvailableCandidate(page);
  const { email } = await registerEmployer(page);
  await page.goto("/it/employer/dashboard");

  const jobsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post a Job" }) });
  await jobsCard.getByLabel("Title").fill("E2E Reporting Role");
  await jobsCard.getByRole("button", { name: "Post job" }).click();
  await expect(jobsCard.getByText("Job posted.")).toBeVisible();

  await page.reload();
  const interviewsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Shortlist & Interviews" }) });
  await interviewsCard.getByLabel("Job posting").selectOption({ label: "E2E Reporting Role" });
  await interviewsCard.getByLabel("Candidate").selectOption({ label: name });
  await interviewsCard.getByRole("button", { name: "Shortlist" }).click();
  await expect(interviewsCard.getByText("Candidate shortlisted.")).toBeVisible();

  const shortlistedRow = interviewsCard.locator(".card", { hasText: name });
  // Same accumulated-state collision risk as emp-004-interview-scheduling.spec.ts's own
  // fix -- vary the minute per run against the shared, non-isolated dev DB (RAID.md I-06).
  const uniqueMinute = String(Date.now() % 60).padStart(2, "0");
  await shortlistedRow.getByLabel("Interview date/time").fill(`2027-04-01T10:${uniqueMinute}`);
  await shortlistedRow.getByRole("button", { name: "Schedule interview" }).click();
  await expect(shortlistedRow.getByText("Interview scheduled.")).toBeVisible();

  const interviewCard = page.locator(".grid.two .card", { hasText: name }).last();
  await expect(interviewCard.getByText("Awaiting outcome")).toBeVisible();

  const interviews = await (await page.request.get("/api/v1/employer/interviews")).json();
  const interview = interviews.find((row: { candidate: string }) => row.candidate === name);

  await page.request.post("/api/v1/auth/login", { data: { email: "itadmin@edusphere.local", password: "Demo@123", division: "it" } });
  const updated = await page.request.patch(`/api/v1/workflows/it/interviews/${interview.id}`, { data: { result: "cancelled" } });
  expect(updated.ok()).toBeTruthy();

  await loginAsEmployer(page, email);
  await page.goto("/it/employer/dashboard");
  const cancelledCard = page.locator(".grid.two .card", { hasText: name }).last();
  await expect(cancelledCard.getByText("cancelled")).toBeVisible();
});

test("the interview list requires an employer session", async ({ page }) => {
  const response = await page.request.get("/api/v1/employer/interviews");
  expect(response.status()).toBe(401);
});
