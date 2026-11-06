import { expect, test, type Browser, type Page } from "@playwright/test";

// hrc-031 (DEC-SCOPE-412): every §11 section in both portals (AC) -- an external candidate follows an application through My applications,
// Interviews, Notifications (type filter) and Documents; a student reads the new sections; each portal refuses the other's role.
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const PASSWORD = "Candidate@12345";

async function signIn(page: Page, email: string, portal = "/it/login", password = "Demo@123") {
  await page.goto(portal);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function asAdmin<T>(browser: Browser, work: (page: Page) => Promise<T>): Promise<T> {
  const admin = await browser.newContext();
  const page = await admin.newPage();
  await signIn(page, "superadmin@edusphere.local", "/admin/login");
  const out = await work(page);
  await admin.close();
  return out;
}

async function openRequirement(browser: Browser, title: string): Promise<string> {
  return asAdmin(browser, async ({ request }) => {
    const company = await request.post("/api/v1/recruiter/companies", { data: { name: `HRC31 Co ${Date.now()}-${Math.random().toString(36).slice(2, 7)}` } });
    expect(company.ok(), await company.text()).toBeTruthy();
    const created = await request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title, location: "Pune", work_mode: "hybrid" } });
    expect(created.ok(), await created.text()).toBeTruthy();
    const id = (await created.json()).requirement.id as string;
    expect((await request.post(`/api/v1/recruiter/requirements/${id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
    return id;
  });
}

async function newCandidate(page: Page): Promise<string> {
  const n = () => Math.floor(Math.random() * 65535).toString(16);
  await page.context().setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8::${n()}:${n()}` }); // the context's: page.request ignores the page's headers
  const email = `hrc031-${Date.now()}-${n()}@example.com`;
  const registered = await page.request.post("/api/v1/candidate/register", { data: { full_name: "Asha Portal", email, password: PASSWORD, consent_version: "candidate-v1" } });
  expect(registered.status(), await registered.text()).toBe(202);
  const token = (await registered.json()).development_verification_token as string;
  expect((await page.request.post("/api/v1/candidate/verify-email", { data: { token } })).ok()).toBeTruthy();
  await signIn(page, email, "/it/login", PASSWORD);
  return email;
}

const nav = (page: Page, name: string) => page.getByRole("link", { name, exact: true }).first();

test("a candidate follows an application through every section of their portal", async ({ page, browser }) => {
  const title = `HRC31 Analyst ${Date.now()}`;
  const jobId = await openRequirement(browser, title);
  const email = await newCandidate(page);

  await nav(page, "My applications").click();
  await expect(page).toHaveURL(/\/it\/careers\/portal\/applications$/);
  await expect(page.getByText("You haven't applied to any jobs yet.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "My offers" })).toBeVisible();
  await expect(page.getByText("role-scoped")).toHaveCount(0);

  const applied = await page.request.post(`/api/v1/candidate/jobs/${jobId}/apply`);
  expect(applied.status(), await applied.text()).toBe(201);
  const { id: applicationId, code } = await applied.json();
  await page.reload();
  const row = page.getByRole("row").filter({ hasText: code });
  await expect(row).toContainText(title);
  await expect(row).toContainText("Received");
  await expect(row).toContainText("No action needed");
  await expect(page.getByRole("columnheader", { name: "Applied on" })).toBeVisible();

  await nav(page, "Interviews").click();
  await expect(page.getByText("No interviews are scheduled yet.")).toBeVisible();
  const when = new Date(Date.now() + 4 * 86400000).toISOString();
  await asAdmin(browser, async ({ request }) => {
    const made = await request.post("/api/v1/recruiter/interviews", { data: { application_id: applicationId, round: "hr_round", scheduled_at: when, mode: "Online", meeting_url: "https://meet.example.com/hrc031", notify: true } });
    expect(made.status(), await made.text()).toBe(201);
  });
  await page.reload();
  await expect(page.getByRole("row").filter({ hasText: title })).toContainText("HR Round");
  await expect(page.getByRole("link", { name: /meeting link/ })).toHaveAttribute("href", "https://meet.example.com/hrc031");

  await nav(page, "My applications").click();
  await expect(page.getByRole("row").filter({ hasText: code })).toContainText("Attend your interview:");

  await nav(page, "My results").click();
  await expect(page.getByText("No interview results yet.")).toBeVisible();

  await nav(page, "Documents").click();
  await expect(page.getByRole("heading", { name: "Your documents", level: 3 })).toBeVisible();
  await expect(page.getByText("Nothing has been requested from you.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload document" })).toBeVisible();

  await nav(page, "Notifications").click();
  const type = page.getByLabel("Type");
  await expect(type).toBeVisible();
  await type.selectOption("Interview scheduled");
  await expect(page.getByText(/^Showing 1 of /)).toBeVisible();
  const notice = page.getByRole("link", { name: /Interview scheduled/ }).first();
  await expect(notice).toHaveAttribute("href", "/it/careers/portal/interviews");
  await expect(page.getByRole("link", { name: "Notification preferences" })).toBeVisible();

  await nav(page, "Privacy").click();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Change your contact details" })).toHaveAttribute("href", "/it/careers/portal/profile");
  await expect(page.getByRole("button", { name: "Leave the candidate pool" })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["applications", "interviews", "results", "documents", "notifications", "privacy"]) {
    await page.goto(`/it/careers/portal/${path}`);
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
    expect(await noSideScroll(page), path).toBe(true);
  }
  await page.goto("/it/careers/portal/applications"); // QA-04: the next action is on the phone's screen, not off to the side
  const cell = await page.locator("td[data-label='Next action']").first().boundingBox();
  expect((cell?.x ?? 0) + (cell?.width ?? 9999)).toBeLessThanOrEqual(390);

  await page.goto("/it/student/results"); // the other portal is refused
  await expect(page.getByRole("heading", { name: "My Results", level: 2 })).toHaveCount(0);
});

test("a student reads the new sections and the candidate portal refuses them", async ({ page }) => {
  await signIn(page, "student.it@edusphere.local");
  await nav(page, "Job Applications").click();
  await expect(page.getByRole("heading", { name: "My results" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "My offers" })).toBeVisible();

  await nav(page, "Results").click();
  await expect(page).toHaveURL(/\/it\/student\/results$/);
  await expect(page.getByRole("heading", { name: "My Results", level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "My results", level: 3 })).toBeVisible();

  await nav(page, "Documents").click();
  await expect(page.getByRole("heading", { name: "Documents for placement" })).toBeVisible();

  await nav(page, "Privacy").click();
  await expect(page.getByText("student.it@edusphere.local").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Contact details" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /placement candidate pool/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Request a copy of my data" })).toBeVisible();

  await nav(page, "Notifications").click();
  await expect(page.getByRole("link", { name: "Notification preferences" })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  for (const section of ["results", "documents", "privacy", "job-applications"]) {
    await page.goto(`/it/student/${section}`);
    await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
    expect(await noSideScroll(page), section).toBe(true);
  }

  await page.goto("/it/careers/portal/results");
  await expect(page.getByRole("heading", { name: "My Results", level: 2 })).toHaveCount(0);
});
