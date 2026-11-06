import { expect, test, type Page } from "@playwright/test";

// hrc-033 (DEC-SCOPE-414; AC: each figure equals its drill-down, the funnel is monotonic): the seeded recruiter adds a company and a requirement,
// narrows the Vacancy board to that employer, opens the Open figure and lands on the requirement. Every figure of every board is compared with
// its records through the same API the page reads. The HR Manager reaches the boards from the menu; a student gets the access card.

async function signIn(page: Page, email: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const PATH = "/recruiter/recruitment-dashboards";
const API = "/api/v1/recruiter/recruitment-dashboards";
const BOARDS = ["funnel", "vacancy", "recruiter", "officer", "interview"];
type Payload = { sections: { figures: { key: string; label: string; value: number }[] }[] };

test("a recruiter narrows a board, opens a figure's records and reaches the record", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const failed: string[] = [];
  page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && failed.push(r.url()));
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, "placement@edusphere.local", "/recruiter/dashboard");
  const name = `E2E Hrc033 ${stamp} Ltd`;
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `E2E Dash ${stamp}`, location: "Pune" } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const requirement = (await created.json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }

  await page.goto(PATH);
  await page.waitForURL(`**${PATH}/funnel`);
  await page.getByRole("navigation", { name: "Recruitment dashboards" }).getByRole("link", { name: "Vacancy" }).click();
  await page.waitForURL(`**${PATH}/vacancy`);
  await page.getByLabel("Employer").selectOption({ label: name });
  await page.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(/employer=/);
  expect(page.url()).not.toContain("owner=");

  await page.getByRole("link", { name: /^Open: 1\./ }).click();
  await page.waitForURL(/drill=open/);
  await expect(page.getByRole("heading", { name: "Open: 1 record" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Open: 1 record" })).toBeVisible();
  await page.getByRole("link", { name: requirement.code }).click();
  await page.waitForURL(`**/recruiter/requirements/${requirement.id}`);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Open: 1 record" })).toBeVisible();

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  expect(download.suggestedFilename()).toBe("recruitment-vacancy.csv");

  await page.setViewportSize({ width: 375, height: 800 });
  await expect(page.getByRole("heading", { name: "Open: 1 record" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  // QA-01: a long value beside it must not squeeze a label ("Employe / r").
  const labelShrink = await page.locator("#records td").first().evaluate((td) => getComputedStyle(td, "::before").flexShrink);
  expect(labelShrink).toBe("0");

  expect(failed).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("every figure of every board equals its records, and the funnel never grows", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page, "hr.manager@edusphere.local", "/it/hr-manager/dashboard");
  for (const board of BOARDS) {
    const payload = (await (await page.request.get(`${API}/${board}`)).json()) as Payload;
    const figures = payload.sections.flatMap((s) => s.figures);
    expect(figures.length).toBeGreaterThan(0);
    for (const figure of figures) {
      const drill = await (await page.request.get(`${API}/${board}/drill/${figure.key}?limit=1`)).json();
      expect(drill.total, `${board}/${figure.key}`).toBe(figure.value);
    }
    if (board === "funnel") {
      const counts = figures.map((f) => f.value);
      expect(counts).toEqual([...counts].sort((a, b) => b - a));
    }
  }
});

test("the HR Manager reaches the boards from the menu and a student cannot", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "hr.manager@edusphere.local", "/it/hr-manager/dashboard");
  await page.getByRole("link", { name: "Recruitment dashboards", exact: true }).first().click();
  await page.waitForURL(`**${PATH}/funnel`);
  await expect(page.getByRole("heading", { name: "Recruitment funnel" })).toBeVisible();
  await expect(page.getByLabel("Branch")).toBeDisabled();

  await page.goto(`${PATH}/interview?to=2099-01-01`);
  await expect(page.locator(".form-error")).toContainText("future");

  await signIn(page, "student.it@edusphere.local", "/it/student/dashboard");
  await page.goto(`${PATH}/funnel`);
  await expect(page.getByText("Your role has no recruitment dashboards")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Recruitment dashboards" })).toHaveCount(0);
});
