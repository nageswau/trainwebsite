import { test, expect } from "@playwright/test";

// EMP-004 -- Interview scheduling and shortlist. Requires the stack running via
// `docker compose up`. Creates its own throwaway Employer + a real candidate (the
// seeded IT student, made an available candidate the same way EMP-003's own spec does)
// per test.

async function registerEmployer(page: import("@playwright/test").Page) {
  const unique = Date.now();
  const response = await page.request.post("/api/v1/employer/register", {
    data: {
      email: `emp004-e2e-${unique}@example.local`,
      password: "Sup3r-Secret-Pass!",
      full_name: "E2E Employer",
      company_name: `E2E Hiring ${unique}`,
      company_website: "https://example.com",
    },
  });
  expect(response.ok()).toBeTruthy();
}

async function ensureSeededStudentIsAnAvailableCandidate(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "student.it@edusphere.local", password: "Demo@123", division: "it" } });
  const student = await (await page.request.get("/api/v1/auth/me")).json();
  await page.request.post("/api/v1/auth/login", { data: { email: "itadmin@edusphere.local", password: "Demo@123", division: "it" } });
  await page.request.put(`/api/v1/workflows/it/placement/profiles/${student.id}`, { data: { available: true, withdrawn: false } });
  return { name: student.full_name as string };
}

test("employer shortlists a candidate for their own posting and schedules an interview (EMP-004-AC01)", async ({ page }) => {
  const { name } = await ensureSeededStudentIsAnAvailableCandidate(page);
  await registerEmployer(page);
  await page.goto("/it/employer/dashboard");

  const jobsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post a Job" }) });
  await jobsCard.getByLabel("Title").fill("E2E Hiring Role");
  await jobsCard.getByRole("button", { name: "Post job" }).click();
  await expect(jobsCard.getByText("Job posted.")).toBeVisible();

  // EmployerInterviewsPanel fetches its own job list independently on mount -- reload
  // so it picks up the posting just created in the sibling panel above.
  await page.reload();
  const interviewsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Shortlist & Interviews" }) });
  await interviewsCard.getByLabel("Job posting").selectOption({ label: "E2E Hiring Role" });
  await interviewsCard.getByLabel("Candidate").selectOption({ label: name });
  await interviewsCard.getByRole("button", { name: "Shortlist" }).click();
  await expect(interviewsCard.getByText("Candidate shortlisted.")).toBeVisible();

  const shortlistedRow = interviewsCard.locator(".card", { hasText: name });
  await expect(shortlistedRow).toBeVisible();
  // A fixed instant collides with the same seeded candidate's interview from an earlier
  // run of this exact spec, since the shared dev DB has no test-isolation (RAID.md
  // I-06) and the backend's own conflict check (EMP-004-AC02) rejects a second interview
  // for the same candidate at the exact same instant -- vary the minute per run instead.
  const uniqueMinute = String(Date.now() % 60).padStart(2, "0");
  await shortlistedRow.getByLabel("Interview date/time").fill(`2027-03-01T10:${uniqueMinute}`);
  await shortlistedRow.getByRole("button", { name: "Schedule interview" }).click();
  await expect(shortlistedRow.getByText("Interview scheduled.")).toBeVisible();
});

test("employer dashboard's shortlist panel requires an employer session", async ({ page }) => {
  await page.goto("/it/employer/dashboard");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});
