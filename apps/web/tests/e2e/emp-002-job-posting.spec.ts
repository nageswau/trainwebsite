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

test("a new posting starts as a draft, and publishing makes it visible to students (EMP-002-AC01)", async ({ page }) => {
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

  await posting.getByRole("button", { name: "Publish" }).click();
  await expect(posting.getByText("Visible to students")).toBeVisible();
});

test("employer closes their own published posting and it stops showing as visible (EMP-002-AC02)", async ({ page }) => {
  await registerEmployer(page);
  await page.goto("/it/employer/dashboard");

  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Post a Job" }) });
  await card.getByLabel("Title").fill("E2E Role To Close");
  await card.getByRole("button", { name: "Post job" }).click();
  await expect(card.getByText("Job posted.")).toBeVisible();

  const posting = card.locator(".card", { hasText: "E2E Role To Close" });
  await posting.getByRole("button", { name: "Publish" }).click();
  await expect(posting.getByText("Visible to students")).toBeVisible();
  await posting.getByRole("button", { name: "Close posting" }).click();
  await expect(posting.getByText("Closed")).toBeVisible();
});

test("employer dashboard requires an employer session", async ({ page }) => {
  await page.goto("/it/employer/dashboard");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});
