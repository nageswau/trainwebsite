import { test, expect } from "@playwright/test";

// EMP-002 -- Job posting. Requires the stack running via `docker compose up`. Registers
// its own throwaway Employer account per test (via the real API, which also logs it in)
// rather than depending on any shared seed data -- no Employer account is seeded.

async function registerEmployer(page: import("@playwright/test").Page) {
  const unique = Date.now();
  const response = await page.request.post("/api/v1/employer/register", {
    data: {
      email: `emp002-e2e-${unique}@example.local`,
      password: "Sup3r-Secret-Pass!",
      full_name: "E2E Employer",
      company_name: `E2E Jobs ${unique}`,
      company_website: "https://example.com",
    },
  });
  expect(response.ok()).toBeTruthy();
}

// hrc-007 (DEC-SCOPE-380 A4): Publish now sends an employer's posting for approval; the seeded HR Manager approves it through the API.
async function publishAndApprove(page: import("@playwright/test").Page, browser: import("@playwright/test").Browser, posting: import("@playwright/test").Locator, title: string) {
  await posting.getByRole("button", { name: "Publish" }).click();
  await expect(posting.getByText("Awaiting approval")).toBeVisible();
  const jobs = (await (await page.request.get("/api/v1/employer/jobs")).json()) as { id: string; title: string }[];
  const job = jobs.find((j) => j.title === title)!;
  const hr = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  expect((await hr.request.post("/api/v1/auth/login", { data: { email: "hr.manager@edusphere.local", password: "Demo@123", division: "it" } })).ok()).toBeTruthy();
  expect((await hr.request.post(`/api/v1/recruiter/requirements/${job.id}/approve`, { data: {} })).ok()).toBeTruthy();
  await hr.close();
  await page.reload();
}

test("a new posting starts as a draft, and publishing (once approved) makes it visible to students (EMP-002-AC01)", async ({ page, browser }) => {
  await registerEmployer(page);
  await page.goto("/it/employer/dashboard");

  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post a Job" }) });
  await card.getByLabel("Title").fill("E2E Backend Engineer");
  await card.getByLabel("Skills (comma separated)").fill("Python, FastAPI");
  await card.getByRole("button", { name: "Post job" }).click();
  await expect(card.getByText("Job posted.")).toBeVisible();

  const posting = card.locator(".card", { hasText: "E2E Backend Engineer" });
  await expect(posting).toBeVisible();
  await expect(posting.getByText("Draft")).toBeVisible();

  await publishAndApprove(page, browser, posting, "E2E Backend Engineer");
  await expect(posting.getByText("Visible to students")).toBeVisible();
});

test("employer closes their own published posting and it stops showing as visible (EMP-002-AC02)", async ({ page, browser }) => {
  await registerEmployer(page);
  await page.goto("/it/employer/dashboard");

  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post a Job" }) });
  await card.getByLabel("Title").fill("E2E Role To Close");
  await card.getByRole("button", { name: "Post job" }).click();
  await expect(card.getByText("Job posted.")).toBeVisible();

  const posting = card.locator(".card", { hasText: "E2E Role To Close" });
  await publishAndApprove(page, browser, posting, "E2E Role To Close");
  await expect(posting.getByText("Visible to students")).toBeVisible();
  await posting.getByRole("button", { name: "Close posting" }).click();
  await expect(posting.locator(".badge").first()).toHaveText("Closed"); // the visibility badge (the status badge says Closed too)
});

test("employer dashboard requires an employer session", async ({ page }) => {
  await page.goto("/it/employer/dashboard");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});
