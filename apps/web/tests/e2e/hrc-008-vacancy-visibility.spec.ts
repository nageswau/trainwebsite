import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// hrc-008 (DEC-SCOPE-383): the Placement Manager (`jobs.publish`) sets who sees a job from its detail page. Internal hides it from the
// careers page and the student portal (AC1); Public brings it back (+); the public apply route answers 404 for an internal job (-); a
// recruiter without the grant is refused. A throwaway company and requirement per test; seeded demo staff accounts.
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string, portal = "/it/login") {
  await page.goto(portal);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

/** An open, unassigned requirement (so in the placement manager's scope), set up by the Super Admin -- only a requirement's writer opens it. */
async function openRequirement(browser: Browser, title: string): Promise<string> {
  const admin = await browser.newContext();
  const adminPage = await admin.newPage();
  await signIn(adminPage, "superadmin@edusphere.local", "/admin/login");
  const request = adminPage.request;
  const company = await request.post("/api/v1/recruiter/companies", { data: { name: `HRC8 Co ${Date.now()}-${Math.random().toString(36).slice(2, 7)}` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const created = await request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title, location: "Pune" } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).requirement.id as string;
  const opened = await request.post(`/api/v1/recruiter/requirements/${id}/status`, { data: { status: "requirement_received" } });
  expect(opened.ok(), await opened.text()).toBeTruthy();
  await admin.close();
  return id;
}

const careersTitles = async (request: APIRequestContext) => ((await (await request.get("/api/v1/public/jobs")).json()) as { title: string }[]).map((j) => j.title);

test("the placement manager makes a job internal, it leaves the careers page and the portal, and public brings it back", async ({ page, browser }) => {
  const title = `HRC8 Visibility ${Date.now()}`;
  const id = await openRequirement(browser, title);
  await signIn(page, "placement.manager@edusphere.local", "/admin/login");
  await page.goto(`/recruiter/requirements/${id}`);
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visibility" }) });
  await expect(card.locator("strong")).toHaveText("Public website");
  await expect(card.getByRole("button", { name: "Save visibility" })).toBeDisabled();

  await card.getByLabel("Who can see this job").selectOption("internal");
  await expect(card.getByText("Seen by staff only. Candidates cannot see or apply to it.").first()).toBeVisible();
  await card.getByRole("button", { name: "Save visibility" }).click();
  await expect(page.getByText("Visibility saved: Internal only.")).toBeVisible();
  await expect(card.locator("strong")).toHaveText("Internal only");

  const visitor = await browser.newContext();
  const careers = await visitor.newPage();
  await careers.goto("/it/careers");
  const search = careers.getByPlaceholder("Search role, company, location, or skill…");
  await search.fill(title); // the page shows six jobs at a time
  await expect(careers.getByRole("heading", { name: "No matching jobs" })).toBeVisible(); // AC1
  const apply = await careers.request.post(`/api/v1/public/jobs/${id}/apply`, { data: { full_name: "Pat", email: "pat@example.local", resume_url: "https://example.local/cv.pdf" } });
  expect(apply.status()).toBe(404); // -
  const student = await browser.newContext();
  const studentPage = await student.newPage();
  await signIn(studentPage, "student.it@edusphere.local");
  const openJobs = (await (await studentPage.request.get("/api/v1/workflows/it/jobs/open")).json()) as { title: string }[];
  expect(openJobs.map((j) => j.title)).not.toContain(title);

  await card.getByLabel("Who can see this job").selectOption("public");
  await card.getByRole("button", { name: "Save visibility" }).click();
  await expect(page.getByText("Visibility saved: Public website.")).toBeVisible();
  expect(await careersTitles(careers.request)).toContain(title); // +
  await careers.reload();
  await search.fill(title);
  await expect(careers.getByRole("heading", { name: title })).toBeVisible();
  await visitor.close();
  await student.close();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(card.getByLabel("Who can see this job")).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});

test("a segment needs a talent pool, and a recruiter without the grant is refused", async ({ page, browser }) => {
  const title = `HRC8 Segment ${Date.now()}`;
  const id = await openRequirement(browser, title);
  await signIn(page, "placement.manager@edusphere.local", "/admin/login");
  await page.goto(`/recruiter/requirements/${id}`);
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Visibility" }) });
  await card.getByLabel("Who can see this job").selectOption("segment");
  const pool = card.getByLabel("Talent pool");
  await expect(pool).toBeEnabled();
  await card.getByRole("button", { name: "Save visibility" }).click();
  await expect(card.getByRole("alert")).toHaveText("Choose the talent pool that may see this job.");
  await expect(pool).toBeFocused();
  await pool.selectOption({ index: 1 });
  const poolName = (await pool.locator("option:checked").textContent())?.trim();
  await card.getByRole("button", { name: "Save visibility" }).click();
  await expect(page.getByText("Visibility saved: Segment (talent pool).")).toBeVisible();
  await expect(card.locator("strong")).toHaveText(`Segment (talent pool): ${poolName}`);
  expect(await careersTitles(page.request)).not.toContain(title);

  const recruiter = await browser.newContext();
  const recruiterPage = await recruiter.newPage();
  await signIn(recruiterPage, "placement@edusphere.local");
  const refused = await recruiterPage.request.put(`/api/v1/recruiter/requirements/${id}/visibility`, { data: { visibility: "public" } });
  expect(refused.status()).toBe(403);
  expect((await refused.json()).detail).toBe("You cannot change who sees job requirements");
  await recruiter.close();
});
