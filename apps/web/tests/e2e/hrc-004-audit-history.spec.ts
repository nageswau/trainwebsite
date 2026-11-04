import { expect, type Page, test } from "@playwright/test";

// hrc-004 (DEC-SCOPE-376; AC1, AC2): a recruiter edits a requirement's title and salary, and a candidate's location and mobile -- each
// page's Change history then shows the title and location old → new, and the salary and mobile as "changed (value hidden)", never values.
const RECRUITER = "placement@edusphere.local";
const API = "/api/v1/recruiter";

async function signIn(page: Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", RECRUITER);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
}

async function created(page: Page, url: string, body: object): Promise<Record<string, unknown>> {
  const response = await page.request.post(url, { data: body });
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}

const history = (page: Page) => page.getByRole("region", { name: "Change history" });

test("a requirement's history shows the title old → new and the salary as changed", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page);
  const company = (await created(page, `${API}/companies`, { name: `E2E Hrc004 ${stamp} Labs` })).company as { id: string };
  const requirement = (await created(page, `${API}/requirements`, { company_id: company.id, title: `Java Dev ${stamp}`, location: "Pune" })).requirement as { id: string };

  await page.goto(`/recruiter/requirements/${requirement.id}`);
  await expect(history(page).getByRole("listitem", { name: "Created" })).toBeVisible(); // its creation, by field name (B8)
  await expect(history(page).getByRole("listitem", { name: "Details edited" })).toHaveCount(0);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Job title (required)").fill(`Senior Java Dev ${stamp}`);
  await page.getByLabel("Salary from (₹ a year)").fill("500000");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();

  const edit = history(page).getByRole("listitem", { name: "Details edited" });
  await expect(edit).toContainText("by Kiran Placement");
  await expect(edit.getByText(`Title: Java Dev ${stamp} → Senior Java Dev ${stamp}`)).toBeVisible(); // AC1
  await expect(edit.getByText("Salary min: changed (value hidden)")).toBeVisible(); // AC2
  await expect(edit).not.toContainText("500000");
  await page.screenshot({ path: test.info().outputPath("requirement-history.png"), fullPage: true });

  await page.reload(); // the history is read from the server, not kept in the page
  await expect(history(page).getByRole("listitem", { name: "Details edited" })).toBeVisible();
});

test("a candidate's history shows the location old → new and the mobile as changed", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page);
  const sources = await (await page.request.get(`${API}/catalogue/candidate-sources`)).json();
  const source = (sources.items ?? sources).find((s: { active?: boolean }) => s.active !== false) as { id: string };
  const candidate = await created(page, `${API}/candidates`, {
    name: `Hrc004 ${stamp}`, mobile: `9${String(stamp).slice(-9)}`, location: "Pune", source_id: source.id,
  }) as { id: string };

  await page.goto(`/recruiter/candidates/${candidate.id}`);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.locator("#cand-location").fill("Chennai");
  await page.locator("#cand-mobile").fill(`8${String(stamp).slice(-9)}`);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();

  const edit = history(page).getByRole("listitem", { name: "Profile edited" });
  await expect(edit.getByText("Location: Pune → Chennai")).toBeVisible();
  await expect(edit.getByText("Mobile: changed (value hidden)")).toBeVisible();
  await expect(edit).not.toContainText(String(stamp).slice(-9));
});
