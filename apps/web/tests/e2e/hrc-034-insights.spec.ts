import { expect, test, type Page } from "@playwright/test";

// hrc-034 (DEC-SCOPE-416): a student sees and applies to a job and the HR Manager's Portal analytics counts it; Skill demand flags a skill with no
// supply; Data quality's figures open their records; a recruiter is refused. Each figure's arithmetic is covered by test_hrc_034_insights.py.

async function signIn(page: Page, email: string, landing: string, login = "/it/login", password = "Demo@123") {
  await page.context().clearCookies();
  await page.goto(login);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const STUDENT = "student.it@edusphere.local";
const HR_MANAGER = "hr.manager@edusphere.local";

function peopleCell(page: Page, step: string) {
  return page.getByRole("row", { name: new RegExp(step) }).getByRole("cell").first();
}

test("a student's view and application reach Portal analytics, without inflating on refresh", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.goto("/recruiter/insights/portal-analytics");
  const events = page.getByRole("row", { name: /Viewed a job/ }).getByRole("cell").last();
  const before = await events.isVisible() ? Number(await events.textContent()) : 0;

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Hrc034 ${stamp} Ltd` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `Insights Role ${stamp}`, location: "Pune", description: "E2E" } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const requirement = (await created.json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }

  await signIn(page, STUDENT, "/it/student/dashboard");
  await page.goto(`/it/student/jobs?view=all&q=${stamp}`);
  await expect(page.getByRole("heading", { name: `Insights Role ${stamp}` })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: `Insights Role ${stamp}` })).toBeVisible();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText(/^Applied/)).toBeVisible();

  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.getByRole("link", { name: "Recruitment insights" }).first().click();
  await page.waitForURL("**/recruiter/insights/skill-demand");
  await page.getByRole("link", { name: "Portal analytics" }).click();
  await page.waitForURL("**/recruiter/insights/portal-analytics");
  await expect(events).toHaveText(String(before + 1)); // the refresh did not count twice
  expect(Number(await peopleCell(page, "Submitted an application").textContent())).toBeGreaterThanOrEqual(1);
});

test("a period the API refuses keeps the page and says why", async ({ page }) => {
  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.goto("/recruiter/insights/portal-analytics?from=2026-05-02&to=2026-05-01");
  await expect(page.locator(".form-error")).toHaveText("The start date must not be after the end date");
  await expect(page.getByLabel("From")).toBeVisible();
});

test("Skill demand flags a skill with no supply, and N changes the vacancy list", async ({ page }) => {
  test.setTimeout(240_000);
  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.goto("/recruiter/insights/skill-demand");
  await expect(page.getByRole("heading", { name: "Skill demand", exact: true })).toBeVisible();
  const table = page.getByRole("table", { name: "Demand and supply by skill" });
  const zero = page.locator(".kpi-tile").filter({ hasText: "Skills with zero supply" }).locator(".kpi-value");
  if (Number(await zero.textContent()) > 0) await expect(table.locator(".badge.zero-supply").first()).toHaveText("No supply");
  await page.getByLabel("Fewer than").fill("1");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL("**/recruiter/insights/skill-demand?n=1");
  await expect(page.getByText("Open jobs with fewer than 1 candidate through")).toBeVisible();
  await page.getByRole("link", { name: "Largest supply" }).click();
  await page.waitForURL("**sort=supply&n=1");
  await expect(page.getByLabel("Fewer than")).toHaveValue("1");
});

test("Data quality opens a figure's records, and the refused roles see the access card", async ({ page }) => {
  test.setTimeout(240_000);
  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.goto("/recruiter/insights/data-quality");
  const tile = page.locator(".kpi-tile").filter({ hasText: "Jobs missing fields" });
  const value = (await tile.locator(".kpi-value").textContent())?.trim();
  await page.getByRole("link", { name: "Show what Jobs missing fields counts" }).click();
  await page.waitForURL("**figure=jobs_missing_fields");
  await expect(page.getByRole("heading", { name: `Jobs missing fields (${value})` })).toBeVisible();
  await expect(page.getByRole("link", { name: "Fix Failed notifications" })).toHaveAttribute("href", "/recruiter/notification-exceptions");

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/insights/data-quality");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByText("You cannot read the recruitment insights")).toBeVisible();
});
