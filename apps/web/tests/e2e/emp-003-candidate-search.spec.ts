import { test, expect } from "@playwright/test";

// EMP-003 -- Candidate profile search. Requires the stack running via `docker compose
// up` with `python -m app.seed` already applied. No `PlacementProfile` is seeded by
// default, so this creates one for the seeded demo IT student via the real admin API
// (not a shared seed row, and reversible -- `available` is just flipped true).

async function ensureSeededStudentIsAnAvailableCandidate(page: import("@playwright/test").Page) {
  await page.request.post("/api/v1/auth/login", { data: { email: "student.it@edusphere.local", password: "Demo@123", division: "it" } });
  const student = await (await page.request.get("/api/v1/auth/me")).json();

  await page.request.post("/api/v1/auth/login", { data: { email: "itadmin@edusphere.local", password: "Demo@123", division: "it" } });
  const updated = await page.request.put(`/api/v1/workflows/it/placement/profiles/${student.id}`, { data: { available: true, withdrawn: false } });
  expect(updated.ok()).toBeTruthy();

  return { name: student.full_name as string };
}

async function registerEmployer(page: import("@playwright/test").Page) {
  const unique = Date.now();
  const response = await page.request.post("/api/v1/employer/register", {
    data: {
      email: `emp003-e2e-${unique}@example.local`,
      password: "Sup3r-Secret-Pass!",
      full_name: "E2E Employer",
      company_name: `E2E Search ${unique}`,
      company_website: "https://example.com",
    },
  });
  expect(response.ok()).toBeTruthy();
}

test("employer searches candidates and sees an available candidate's allowlisted fields (EMP-003-AC01)", async ({ page }) => {
  const { name } = await ensureSeededStudentIsAnAvailableCandidate(page);
  await registerEmployer(page);
  await page.goto("/it/employer/dashboard");

  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Search Candidates" }) });
  await card.getByLabel("Search by name, course, or skill").fill(name);
  const candidateCard = card.locator(".card", { hasText: name });
  await expect(candidateCard).toBeVisible();
  await expect(candidateCard.getByText("Available")).toBeVisible();
});

test("candidate search never surfaces raw contact info (EMP-003-AC02)", async ({ page }) => {
  const { name } = await ensureSeededStudentIsAnAvailableCandidate(page);
  await registerEmployer(page);

  const response = await page.request.get("/api/v1/employer/candidates", { params: { q: name } });
  const body = await response.json();
  const text = JSON.stringify(body);
  expect(text).not.toContain("@edusphere.local");
});

test("employer dashboard's candidate search requires an employer session", async ({ page }) => {
  await page.goto("/it/employer/dashboard");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});
