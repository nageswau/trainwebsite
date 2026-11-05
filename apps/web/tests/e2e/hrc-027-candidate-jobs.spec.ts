import { expect, test, type Browser, type Page } from "@playwright/test";

// hrc-027 (DEC-SCOPE-398): the Jobs page in both portals. A student finds a just-opened job under All open jobs (AC2) with its
// explanation (AC3) and the disclaimer (AC4), applies once and sees the Application ID; an external candidate without skills gets the
// add-skills prompt. A throwaway requirement per test (opened by the Super Admin); seeded demo student.
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string, portal = "/it/login", password = "Demo@123") {
  await page.goto(portal);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function openRequirement(browser: Browser, title: string): Promise<string> {
  const admin = await browser.newContext();
  const adminPage = await admin.newPage();
  await signIn(adminPage, "superadmin@edusphere.local", "/admin/login");
  const request = adminPage.request;
  const company = await request.post("/api/v1/recruiter/companies", { data: { name: `HRC27 Co ${Date.now()}-${Math.random().toString(36).slice(2, 7)}` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const created = await request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title, location: "Pune", work_mode: "hybrid" } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).requirement.id as string;
  const opened = await request.post(`/api/v1/recruiter/requirements/${id}/status`, { data: { status: "requirement_received" } });
  expect(opened.ok(), await opened.text()).toBeTruthy();
  await admin.close();
  return id;
}

test("a student finds an open job under All open jobs, reads why, applies once and sees the Application ID", async ({ page, browser }) => {
  const title = `HRC27 Analyst ${Date.now()}`;
  await openRequirement(browser, title);
  await signIn(page, "student.it@edusphere.local");
  await page.getByRole("link", { name: "Jobs", exact: true }).first().click();
  await expect(page).toHaveURL(/\/it\/student\/jobs$/);
  await expect(page.getByRole("heading", { name: "Jobs", level: 2 })).toBeVisible();
  await expect(page.getByText(/not a guarantee/)).toBeVisible(); // AC4

  await page.getByLabel("Search jobs").fill(title);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: /^All open jobs \(1\)$/ }).click();
  await expect(page).toHaveURL(/view=all/);
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: title }) });
  await expect(card).toContainText("Pune · Hybrid"); // AC2
  await expect(card).toContainText("No skills are listed for this job"); // AC3: the explanation of a job that cannot match
  await card.getByRole("button", { name: "Apply" }).click();
  await expect(card.getByRole("status")).toContainText(/Applied · JA-\d+ · Received/);

  await page.reload(); // the application survives a refresh and the button does not come back
  await expect(card.getByRole("status")).toContainText("Received");
  await expect(card.getByRole("button", { name: "Apply" })).toHaveCount(0);
  const again = await page.request.get(`/api/v1/candidate/jobs?view=all&q=${encodeURIComponent(title)}`);
  expect(((await again.json()).items as { application: unknown }[])[0].application).not.toBeNull();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(card.getByRole("heading", { name: title })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});

test("an external candidate without skills gets the add-skills prompt, and staff are refused", async ({ page, browser }) => {
  const n = () => Math.floor(Math.random() * 65535).toString(16);
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8::${n()}:${n()}` });
  const email = `hrc027-${Date.now()}@example.com`;
  const registered = await page.request.post("/api/v1/candidate/register", {
    data: { full_name: "Ravi Portal", email, password: "Candidate@12345", consent_version: "candidate-v1" },
  });
  expect(registered.status(), await registered.text()).toBe(202);
  const token = (await registered.json()).development_verification_token as string;
  expect((await page.request.post("/api/v1/candidate/verify-email", { data: { token } })).ok()).toBeTruthy();
  await signIn(page, email, "/it/login", "Candidate@12345");
  await page.getByRole("link", { name: "Jobs", exact: true }).first().click();
  await expect(page).toHaveURL(/\/it\/careers\/portal\/jobs$/);
  await expect(page.getByRole("link", { name: /^Recommended for you \(0\)$/ })).toHaveAttribute("aria-current", "page");
  const prompt = page.getByRole("status").filter({ hasText: "Recommendations appear once your skills are on your profile." });
  await expect(prompt).toBeVisible();
  await prompt.getByRole("link", { name: "All open jobs" }).click();
  await expect(page).toHaveURL(/view=all/);
  await expect(page.getByText(/^Showing 1–/)).toBeVisible();

  const staff = await browser.newContext();
  const staffPage = await staff.newPage();
  await signIn(staffPage, "superadmin@edusphere.local", "/admin/login");
  expect((await staffPage.request.get("/api/v1/candidate/jobs")).status()).toBe(403);
  await staff.close();
});
