import { expect, test, type Page } from "@playwright/test";

// mgmt-025 (§21, spec RC1-RC12, M13): the partner opens the Recruitment dashboard from the Command Center, sees the eleven §21 KPIs and the
// company pipeline, and changes the URL-held period; the super admin sees it without revenue and its totals equal rec-035's; the
// accountant is refused. Seeded demo accounts. The shared stack DB also holds backend-test rows, so the checks are relational.

const KPIS = [
  "Recruiters", "Employer partners", "New companies", "Job openings", "Internship openings", "Candidates", "Interviews", "Selections",
  "Joining", "Placement rate", "Revenue",
]; // prettier-ignore

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a partner opens the dashboard from the Command Center and changes the period", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "Students" }).getByRole("link", { name: "Recruitment" }).click();
  await page.waitForURL("**/management/recruitment");
  await expect(page.getByRole("heading", { level: 2, name: "Recruitment" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Recruiter KPIs" }).getByRole("listitem").locator("span")).toHaveText(KPIS);
  await expect(page.getByRole("list", { name: "Company pipeline" }).locator(".funnel-label")).toHaveText([
    "Lead", "Meeting", "Requirement", "Candidate", "Interview", "Selection", "Joining",
  ]); // prettier-ignore

  const form = page.getByRole("form", { name: "Recruitment period" });
  const firstOfMonth = await form.getByLabel("From").inputValue();
  const today = await form.getByLabel("To").inputValue();
  expect(firstOfMonth).toBe(today.slice(0, 8) + "01");
  await form.getByLabel("From").fill(today);
  await form.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(`**/management/recruitment?date_from=${today}&date_to=${today}`);
  await page.reload();
  await expect(page.getByRole("form", { name: "Recruitment period" }).getByLabel("From")).toHaveValue(today);
  await page.getByRole("link", { name: "This month" }).click();
  await page.waitForURL(/\/management\/recruitment$/);
  await expect(page.getByRole("form", { name: "Recruitment period" }).getByLabel("From")).toHaveValue(firstOfMonth);
});

test("the People pillar's Recruiters entry lands on the KPI tiles", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "People" }).getByRole("link", { name: "Recruiters" }).click();
  await page.waitForURL("**/management/recruitment#recruitment-kpis");
  await expect(page.getByRole("list", { name: "Recruiter KPIs" })).toBeInViewport();
});

test("the Partnerships pillar's Companies entry lands on the company pipeline", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.getByRole("region", { name: "Partnerships" }).getByRole("link", { name: "Companies" }).click();
  await page.waitForURL("**/management/recruitment#company-pipeline");
  await expect(page.getByRole("heading", { name: "Company pipeline" })).toBeInViewport();
});

test("a period ending in the future shows the API's words", async ({ page }) => {
  await signIn(page, "partner.one@edusphere.local", "/management");
  await page.goto("/management/recruitment?date_to=2999-01-01");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("The range can't end in the future");
});

test("the super admin sees it without revenue, and the totals equal rec-035's", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "/admin");
  await page.getByRole("link", { name: "Management recruitment figures" }).first().click();
  await page.waitForURL("**/management/recruitment");
  await expect(page.getByRole("list", { name: "Recruiter KPIs" }).getByRole("listitem")).toHaveCount(10);
  await expect(page.getByText("Revenue is shown to partners.", { exact: false })).toBeVisible();

  const mine = await (await page.request.get("/api/v1/management/recruitment")).json();
  const rec035 = (await (await page.request.get("/api/v1/recruiter/management")).json()).totals;
  expect(mine.kpis.employer_partners).toBe(rec035.companies);
  expect(mine.kpis.job_openings + mine.kpis.internship_openings).toBe(rec035.open_requirements);
  expect([mine.kpis.candidates, mine.kpis.interviews, mine.kpis.selections, mine.kpis.joining]).toEqual([
    rec035.candidates_in_pipeline, rec035.interviews, rec035.selected, rec035.joined,
  ]); // prettier-ignore
});

test("the accountant has no entry, and a direct visit is refused", async ({ page }) => {
  await signIn(page, "accountant@edusphere.local", "/management");
  await expect(page.getByRole("link", { name: "Recruitment", exact: true })).toHaveCount(0);
  expect((await page.request.get("/api/v1/management/recruitment")).status()).toBe(403);
  await page.goto("/management/recruitment");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
