import { expect, test, type Page } from "@playwright/test";

// hrc-001 (DEC-SCOPE-370): candidate compensation follows `candidates.compensation.view` (the recruiter holds it, HR does not), and HR is
// offered no legacy placement write form. Seeded demo accounts; the candidate is created per run.
async function signIn(page: Page, email: string) {
  expect((await page.request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division: "it" } })).ok()).toBeTruthy();
}

async function salariedCandidate(page: Page) {
  await signIn(page, "placement@edusphere.local");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const stamp = Date.now();
  const created = await page.request.post("/api/v1/recruiter/candidates", {
    data: { name: `HRC Salary ${stamp}`, email: `hrc001-${stamp}@example.com`, source_id: sources.items.find((s: { active: boolean }) => s.active).id, current_salary: "612345", expected_salary: "834567" },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

test("the recruiter sees a candidate's salary and the salary filter; HR sees neither (H2)", async ({ page }) => {
  const id = await salariedCandidate(page);
  await page.goto(`/recruiter/candidates/${id}`);
  await expect(page.getByText("Expected salary (per year)")).toBeVisible();
  await expect(page.getByText("8,34,567")).toBeVisible();
  await page.goto("/recruiter/find-candidates");
  await expect(page.getByLabel("Expected salary from (₹ lakhs a year)")).toBeVisible();

  await signIn(page, "hr@edusphere.local");
  await page.goto(`/recruiter/candidates/${id}`);
  await expect(page.getByRole("heading", { name: /HRC Salary/ })).toBeVisible();
  await expect(page.getByText("Expected salary (per year)")).toHaveCount(0);
  await expect(page.getByText("8,34,567")).toHaveCount(0);
  const detail = await (await page.request.get(`/api/v1/recruiter/candidates/${id}`)).json();
  expect(detail).not.toHaveProperty("expected_salary");
  await page.goto("/recruiter/find-candidates");
  await expect(page.getByRole("search", { name: "Find candidates" })).toBeVisible();
  await expect(page.getByLabel("Expected salary from (₹ lakhs a year)")).toHaveCount(0);
});

test("HR is offered no legacy placement write form (H1)", async ({ page }) => {
  await signIn(page, "hr@edusphere.local");
  for (const section of ["job-requirements", "interviews"]) {
    await page.goto(`/it/hr/${section}`);
    await expect(page.locator(".portal-main")).toBeVisible();
    for (const name of ["Create job requirement", "Update job requirement", "Schedule interview", "Record interview result"]) {
      await expect(page.getByRole("heading", { name })).toHaveCount(0);
    }
  }
});
