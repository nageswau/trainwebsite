import { expect, test, type Page } from "@playwright/test";

// rec-010 (DEC-SCOPE-138): the seeded IT student joins the placement candidate pool from Placement Status, an employer then finds them
// in EMP-003, and after they leave the employer no longer does. Needs the stack running with `python -m app.seed` applied. Each test
// starts by putting the student back out of the pool through the real API (opt-out is idempotent), so the order of runs never matters.
const STUDENT = { email: "student.it@edusphere.local", password: "Demo@123", division: "it" };

async function signInStudent(page: Page) {
  expect((await page.request.post("/api/v1/auth/login", { data: STUDENT })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/account/placement-pool/opt-out")).ok()).toBeTruthy();
  return (await (await page.request.get("/api/v1/auth/me")).json()).full_name as string;
}

async function employerSees(page: Page, name: string): Promise<boolean> {
  const unique = `${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
  const registered = await page.request.post("/api/v1/employer/register", {
    data: { email: `rec010-${unique}@example.local`, password: "Sup3r-Secret-Pass!", full_name: "E2E Employer", company_name: `rec-010 ${unique}`, company_website: "https://example.com" },
  });
  expect(registered.ok()).toBeTruthy();
  const results = (await (await page.request.get("/api/v1/employer/candidates", { params: { q: name } })).json()) as { name: string }[];
  return results.some((candidate) => candidate.name === name);
}

test("a student joins the pool, an employer finds them, and leaving hides them again (rec-010 AC1-AC4)", async ({ page }) => {
  const name = await signInStudent(page);
  await page.goto("/it/student/placement-status");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Join the placement candidate pool" }) });
  await expect(card.getByText("Version v1")).toBeVisible();
  const join = card.getByRole("button", { name: "Join the pool" });
  await expect(join).toBeDisabled();
  await card.getByRole("checkbox", { name: "I agree to the consent text above" }).check();
  await join.click();
  await expect(page.getByText("You have joined the placement candidate pool.")).toBeVisible();
  await expect(page.getByText("In the placement pool")).toBeVisible();
  await expect(page.getByLabel("Pool history").getByText(/^Joined · /).first()).toBeVisible();

  await page.reload();
  await expect(page.getByText("In the placement pool")).toBeVisible();
  expect(await employerSees(page, name)).toBe(true);

  expect((await page.request.post("/api/v1/auth/login", { data: STUDENT })).ok()).toBeTruthy(); // back to the student, still in the pool
  await page.goto("/it/student/placement-status");
  await page.getByRole("button", { name: "Leave the pool" }).click();
  await page.getByRole("button", { name: "Yes, leave" }).click();
  await expect(page.getByText("You have left the placement candidate pool.")).toBeVisible();
  await expect(page.getByLabel("Pool history").getByText(/^Left · /).first()).toBeVisible();
  expect(await employerSees(page, name)).toBe(false);
});

test("a student who never joined is not shown to employers (rec-010 AC1)", async ({ page }) => {
  const name = await signInStudent(page);
  expect(await employerSees(page, name)).toBe(false);
});

test("Placement Status requires a student session", async ({ page }) => {
  await page.goto("/it/student/placement-status");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});
