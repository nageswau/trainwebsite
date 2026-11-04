import { expect, test, type Page } from "@playwright/test";

// hrc-010 (DEC-SCOPE-383): a recruiter completes a candidate's §5 profile -- a degree, two jobs (total experience is worked out from them),
// location, preferences -- and sees the completeness meter move; an end date before the start is refused with the row named; HR reads
// the profile without an Edit button; the form fits a phone. Seeded demo accounts; the candidate is created per run.
async function signIn(page: Page, email: string, division = "it") {
  expect((await page.request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division } })).ok()).toBeTruthy();
}

async function newCandidate(page: Page): Promise<string> {
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const stamp = Date.now();
  const created = await page.request.post("/api/v1/recruiter/candidates", {
    data: { name: `HRC Profile ${stamp}`, email: `hrc010-${stamp}@example.com`, source_id: sources.items.find((s: { active: boolean }) => s.active).id },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

test("recruiter adds a degree and two jobs; experience is derived and completeness moves; HR reads only", async ({ page }) => {
  await signIn(page, "placement@edusphere.local");
  const id = await newCandidate(page);
  await page.goto(`/recruiter/candidates/${id}`);
  await expect(page.getByRole("meter", { name: "Profile 0% complete" })).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).click();

  await page.getByRole("button", { name: "+ Add education" }).click();
  const degree = page.getByRole("group", { name: "Education 1" });
  await degree.getByLabel("Degree").fill("B.Tech");
  await degree.getByLabel("Institution").fill("JNTU Hyderabad");
  await degree.getByLabel("Year").fill("2018");
  for (const [n, employer, start, end] of [[1, "Infosys", "2019-01-01", "2019-12-31"], [2, "TCS", "2020-01-01", "2020-12-31"]] as const) {
    await page.getByRole("button", { name: "+ Add employment" }).click();
    const job = page.getByRole("group", { name: `Employment history ${n}` });
    await job.getByLabel("Employer *").fill(employer);
    await job.getByLabel("Start date *").fill(start);
    await job.getByLabel("End date").fill(end);
  }
  await expect(page.getByLabel("Total experience (months)")).toHaveCount(0); // worked out from the jobs
  await page.getByLabel("City").fill("Hyderabad");
  await page.getByLabel("State").fill("Telangana");
  await page.getByLabel("Country").fill("India");
  await page.getByLabel("Preferred roles").fill("Java Developer, Backend Engineer");
  await page.getByLabel("Preferred locations").fill("Pune");
  await page.getByRole("checkbox", { name: "Hybrid" }).check();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();

  await expect(page.getByText("2 yr (from employment history)", { exact: true })).toBeVisible();
  await expect(page.getByText("(from employment history)")).toBeVisible();
  await expect(page.getByRole("region", { name: "Profile" }).getByText("B.Tech · JNTU Hyderabad · 2018")).toBeVisible();
  await expect(page.getByRole("region", { name: "Profile" }).getByText("Hyderabad, Telangana, India")).toBeVisible();
  await expect(page.getByRole("meter", { name: "Profile 45% complete" })).toBeVisible(); // education 15 + experience 15 + preferences 15

  // − an end date before the start is refused, naming the row; nothing is saved
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByRole("group", { name: "Employment history 2" }).getByLabel("End date").fill("2019-06-30");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Employment 2: the end date must be on or after the start date" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("2 yr (from employment history)", { exact: true })).toBeVisible();

  await signIn(page, "hr@edusphere.local");
  await page.goto(`/recruiter/candidates/${id}`);
  await expect(page.getByRole("region", { name: "Profile" }).getByText("B.Tech · JNTU Hyderabad · 2018")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
});

test("the profile form fits a phone without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "placement@edusphere.local");
  const id = await newCandidate(page);
  await page.goto(`/recruiter/candidates/${id}`);
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByRole("button", { name: "+ Add employment" }).click();
  await expect(page.getByRole("group", { name: "Employment history 1" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
