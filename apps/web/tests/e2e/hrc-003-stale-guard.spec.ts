import { type Browser, expect, type Page, test } from "@playwright/test";

// hrc-003 (DEC-SCOPE-370; AC1-AC3): two sessions open the same requirement and candidate. The second save is refused with "This record
// changed since you opened it", Review my changes puts the user's edit over the latest version, and the resave succeeds without losing
// the first user's change. Reload latest drops the edit.
const RECRUITER = "placement@edusphere.local";
const API = "/api/v1/recruiter";

async function session(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", RECRUITER);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
  return page;
}

async function created(page: Page, url: string, body: object): Promise<Record<string, unknown>> {
  const response = await page.request.post(url, { data: body });
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}

test("a stale requirement save is refused, reviewed and saved without losing the other edit", async ({ browser }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const [a, b] = [await session(browser), await session(browser)];
  const company = (await created(a, `${API}/companies`, { name: `E2E Hrc003 ${stamp} Labs` })).company as { id: string };
  const requirement = (await created(a, `${API}/requirements`, { company_id: company.id, title: `Java Dev ${stamp}`, location: "Pune" })).requirement as { id: string };

  await a.goto(`/recruiter/requirements/${requirement.id}`);
  await a.getByRole("button", { name: "Edit", exact: true }).click();
  await b.goto(`/recruiter/requirements/${requirement.id}`);
  await b.getByRole("button", { name: "Edit", exact: true }).click();
  await b.getByLabel("Job location", { exact: true }).fill("Chennai");
  await b.getByRole("button", { name: "Save changes" }).click();
  await expect(b.getByText("Changes saved.")).toBeVisible();

  await a.getByLabel("Job title (required)").fill(`Senior Java Dev ${stamp}`);
  await a.getByRole("button", { name: "Save changes" }).click();
  const notice = a.getByRole("alert").filter({ hasText: "This record changed since you opened it" });
  await expect(notice).toContainText("(by Kiran Placement at");
  await expect(notice).toContainText("Changed: Job location.");
  await expect(notice).toBeFocused();
  await a.screenshot({ path: test.info().outputPath("requirement-conflict.png"), fullPage: true });

  await notice.getByRole("button", { name: "Review my changes" }).click();
  await expect(a.getByLabel("Job title (required)")).toHaveValue(`Senior Java Dev ${stamp}`);
  await expect(a.getByLabel("Job location", { exact: true })).toHaveValue("Chennai");
  await expect(a.getByRole("list", { name: "Your changes" })).toContainText(`Job title: yours “Senior Java Dev ${stamp}”, now on record “Java Dev ${stamp}”`);
  await a.getByRole("button", { name: "Save changes" }).click();
  await expect(a.getByText("Changes saved.")).toBeVisible();
  const details = a.getByRole("region", { name: "Details" });
  await expect(details.getByText("Chennai")).toBeVisible(); // the other session's edit survived
  await expect(a.getByRole("heading", { name: new RegExp(`Senior Java Dev ${stamp}`) })).toBeVisible();
});

test("a stale candidate save offers Reload latest, which drops the edit", async ({ browser }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const [a, b] = [await session(browser), await session(browser)];
  const sources = (await (await a.request.get(`${API}/catalogue/candidate-sources`)).json()) as { items: { id: string }[] };
  const candidate = await created(a, `${API}/candidates`, { name: `Rahul ${stamp}`, email: `hrc003-${stamp}@example.com`, source_id: sources.items[0].id });

  await a.goto(`/recruiter/candidates/${candidate.id}`);
  await a.getByRole("button", { name: "Edit", exact: true }).click();
  await b.goto(`/recruiter/candidates/${candidate.id}`);
  await b.getByRole("button", { name: "Edit", exact: true }).click();
  await b.getByLabel(/^Current company/).fill("Globex");
  await b.getByRole("button", { name: "Save changes" }).click();
  await expect(b.getByRole("button", { name: "Edit", exact: true })).toBeVisible();

  await a.getByLabel(/^Current company/).fill("Initech");
  await a.getByRole("button", { name: "Save changes" }).click();
  const notice = a.getByRole("alert").filter({ hasText: "This record changed since you opened it" });
  await expect(notice).toContainText("Changed: Current company.");
  await notice.getByRole("button", { name: "Reload latest" }).click();
  await expect(a.getByLabel(/^Current company/)).toHaveValue("Globex");
  await expect(a.getByRole("alert").filter({ hasText: "This record changed" })).toHaveCount(0);
  await a.getByRole("button", { name: "Cancel" }).click();
  // QA-02: the page behind the form shows the latest too (the Profile card: hrc-004's Change history also names the value)
  await expect(a.getByRole("region", { name: "Profile" }).getByText("Globex")).toBeVisible();
});
