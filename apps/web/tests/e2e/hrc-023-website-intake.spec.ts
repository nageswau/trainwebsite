import { expect, test, type Page } from "@playwright/test";

// hrc-023 (DEC-SCOPE-387): a visitor arrives from a campaign link, applies to a public job with a resume and the pool consent, and the
// placement manager finds the new candidate -- source Website, the campaign and the website application -- with no import (AC1, AC3,
// AC4). A second application with the same email matches the same candidate (AC2). Each run gets its own client IP header, so the
// per-network throttle (10 an hour) never trips a re-run.
const PDF = { name: "cv.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n") };

async function freshNetwork(page: Page) {
  const n = () => Math.floor(Math.random() * 65535).toString(16);
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8::${n()}:${n()}` });
}

async function signIn(page: Page, email: string, portal: string) {
  await page.goto(portal);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

/** The job's own card (its h3), not the nested form card -- the "Apply online" button is gone once the form opens. */
function jobCard(page: Page, company: string) {
  return page.locator(".card", { has: page.getByRole("heading", { level: 3 }) }).filter({ hasText: company }).first();
}

async function applyOnCareers(page: Page, company: string, name: string, email: string): Promise<string> {
  await page.getByPlaceholder("Search role, company, location, or skill…").fill(company); // the page shows six jobs at a time
  const card = jobCard(page, company);
  await card.getByRole("button", { name: "Apply online" }).click();
  await card.getByLabel("Full name *").fill(name);
  await card.getByLabel("Email *").fill(email);
  await card.getByLabel("Resume *").setInputFiles(PDF);
  await card.getByRole("checkbox").check();
  await card.getByRole("button", { name: "Submit application" }).click();
  const done = card.getByRole("status").filter({ hasText: "Save your tracking code" });
  await expect(done).toBeVisible();
  return (await done.locator("strong").innerText()).trim();
}

test("a campaign visitor's application becomes a Website candidate the placement manager sees without import", async ({ page, browser }) => {
  await freshNetwork(page);
  const jobs = await (await page.request.get("/api/v1/public/jobs")).json();
  expect(jobs.length, "a public job must be open on /it/careers").toBeGreaterThan(0);
  const job = jobs[0];
  const stamp = Date.now();
  const name = `Meera Web ${stamp}`;
  const email = `hrc023-${stamp}@example.com`;

  await page.goto("/it/careers?utm_source=e2e&utm_campaign=hrc023");
  const code = await applyOnCareers(page, job.company, name, email);
  await expect(page.getByRole("link", { name: "create a candidate account" })).toHaveAttribute("href", `/it/careers/register?email=${encodeURIComponent(email)}`);

  // AC2: the same person again (another tab of the same visit) -- one candidate
  await page.reload();
  const second = await applyOnCareers(page, job.company, `${name} again`, email);
  expect(second).not.toBe(code);

  const staff = await browser.newContext();
  const manager = await staff.newPage();
  await signIn(manager, "placement.manager@edusphere.local", "/admin/login");
  await manager.goto("/recruiter/candidates");
  await manager.getByLabel("Search candidates").fill(name);
  await manager.getByRole("button", { name: "Search", exact: true }).click();
  const row = manager.getByRole("row", { name: new RegExp(name) });
  await expect(row).toHaveCount(1); // AC2: matched, not duplicated (the second application's name changes nothing)
  await expect(row).toContainText("Website");
  await row.getByRole("link").first().click();

  await expect(manager.getByRole("heading", { name })).toBeVisible();
  const profile = manager.getByRole("region", { name: "Profile" });
  await expect(profile.getByText("source: e2e · campaign: hrc023")).toBeVisible(); // AC1: the campaign
  await expect(profile.getByText("Job application", { exact: true })).toBeVisible();
  const applications = profile.getByRole("listitem").filter({ hasText: job.title });
  await expect(applications.filter({ hasText: code })).toHaveCount(1);
  await expect(applications.filter({ hasText: second })).toHaveCount(1);
  await staff.close();
});

test("the apply form needs the consent and a resume before it sends anything", async ({ page }) => {
  await freshNetwork(page);
  const jobs = await (await page.request.get("/api/v1/public/jobs")).json();
  expect(jobs.length, "a public job must be open on /it/careers").toBeGreaterThan(0);
  await page.goto("/it/careers");
  await page.getByPlaceholder("Search role, company, location, or skill…").fill(jobs[0].company);
  const card = jobCard(page, jobs[0].company);
  await card.getByRole("button", { name: "Apply online" }).click();
  await card.getByLabel("Full name *").fill("No Consent");
  await card.getByLabel("Email *").fill(`hrc023-nc-${Date.now()}@example.com`);
  await card.getByLabel("Resume *").setInputFiles(PDF);
  let applied = false;
  page.on("request", (request) => { if (request.url().includes("/apply")) applied = true; });
  await card.getByRole("button", { name: "Submit application" }).click();
  expect(await card.getByRole("checkbox").evaluate((box: HTMLInputElement) => box.validity.valueMissing)).toBe(true);
  expect(applied).toBe(false);
  await card.getByRole("button", { name: "Cancel" }).click();
  await expect(card.getByRole("button", { name: "Apply online" })).toBeVisible();
});
