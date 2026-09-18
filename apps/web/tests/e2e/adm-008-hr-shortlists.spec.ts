import { test, expect } from "@playwright/test";

// ADM-008 -- HR Team workspace. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied.

test("HR reviews a requirement's shortlist, and an empty requirement shows a clear empty state (ADM-008-AC01/AC02)", async ({ page }) => {
  // Creating a student account requires IT Admin, not HR -- log in as admin first to
  // create the throwaway candidate, then switch to HR for the actual feature under test.
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  const candidateEmail = `adm008-${Date.now()}@example.com`;
  const createdCandidate = await page.request.post("/api/v1/admin/users", { data: { role: "it_student", email: candidateEmail, full_name: "ADM-008 Candidate" } });
  expect(createdCandidate.ok()).toBeTruthy();

  await page.goto("/it/login");
  await page.fill("#login-email", "hr@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/hr/dashboard");

  // Two fresh, throwaway requirements created via the real API -- one that will get a
  // real applicant, one left empty -- never touching shared seed data.
  const filledTitle = `ADM-008 Filled Role ${Date.now()}`;
  const emptyTitle = `ADM-008 Empty Role ${Date.now()}`;
  const filledJob = await (await page.request.post("/api/v1/workflows/it/jobs", { data: { company_name: `ADM-008 Co ${Date.now()}`, title: filledTitle, location: "Remote" } })).json();
  const emptyJob = await (await page.request.post("/api/v1/workflows/it/jobs", { data: { company_name: `ADM-008 Co ${Date.now()}`, title: emptyTitle, location: "Remote" } })).json();

  await page.goto("/it/login");
  await page.fill("#login-email", candidateEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
  const apply = await page.request.post(`/api/v1/workflows/it/jobs/${filledJob.id}/apply`, { data: {} });
  expect(apply.ok()).toBeTruthy();

  await page.goto("/it/login");
  await page.fill("#login-email", "hr@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/hr/dashboard");

  await page.goto("/it/hr/shortlists");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Requirement shortlist" }) });

  await panel.getByLabel("Hiring requirement").selectOption(filledJob.id);
  await expect(panel.locator("table")).toContainText("ADM-008 Candidate");

  await panel.getByLabel("Hiring requirement").selectOption(emptyJob.id);
  await expect(panel.getByText("No candidates have applied to this requirement yet.")).toBeVisible();
});

test("HR sees and can update a requirement's closing date (tester feedback 2026-09-04, RAID.md I-13)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "hr@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/hr/dashboard");

  const title = `ADM-008 Closing Date Role ${Date.now()}`;
  const job = await (await page.request.post("/api/v1/workflows/it/jobs", { data: { company_name: `ADM-008 Co ${Date.now()}`, title, location: "Remote", closes_on: "2027-03-15" } })).json();

  await page.goto("/it/hr/job-requirements");
  await page.locator("#table-search").fill(title);
  await expect(page.locator("table")).toContainText("2027-03-15");

  const updateCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Update job requirement" }) });
  await updateCard.locator("input[name='job_id']").fill(job.id);
  await updateCard.locator("input[name='closes_on']").fill("2027-09-30");
  await updateCard.getByRole("button", { name: "Update job requirement" }).click();
  await expect(updateCard.getByText("Job requirement updated.")).toBeVisible();

  await page.goto("/it/hr/job-requirements");
  await page.locator("#table-search").fill(title);
  await expect(page.locator("table")).toContainText("2027-09-30");
});

test("HR shortlists page requires authentication", async ({ page }) => {
  await page.goto("/it/hr/shortlists");
  await expect(page).toHaveURL(/\/it\/login/);
});
