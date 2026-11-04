import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// hrc-035 (DEC-SCOPE-396): a portal candidate asks for their data to be deleted (K6); the HR Manager declines with a reason, which the
// candidate reads, then approves a second request, which closes the candidate's account (K3/K7, AC2/AC3). Super admin turns the
// retention rule on and off; the HR Manager only reads it (K8, AC5/AC6). A recruiter records the basis when adding a candidate (K1/K2).
// Throwaway candidates per run (own client IP, so hrc-022's registration throttle never trips); seeded demo staff accounts.
const PASSWORD = "Candidate@12345";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function candidate(request: APIRequestContext): Promise<string> {
  const n = () => Math.floor(Math.random() * 65535).toString(16);
  const email = `hrc035-${Date.now()}-${n()}@example.com`;
  const registered = await request.post("/api/v1/candidate/register", {
    data: { full_name: "Asha Privacy", email, password: PASSWORD, consent_version: "candidate-v1" },
    headers: { "X-Forwarded-For": `2001:db8::${n()}:${n()}` },
  });
  expect(registered.status()).toBe(202);
  const token = (await registered.json()).development_verification_token;
  expect((await request.post("/api/v1/candidate/verify-email", { data: { token } })).ok()).toBeTruthy();
  return email;
}

async function signIn(page: Page, email: string, password = "Demo@123") {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function asStaff(browser: Browser, email: string) {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, email);
  return page;
}

async function requestDeletion(page: Page) {
  await page.goto("/it/careers/portal/privacy");
  await page.getByRole("button", { name: "Request deletion" }).click();
  await page.getByRole("checkbox", { name: /cannot be undone/ }).check();
  await page.getByRole("button", { name: "Send deletion request" }).click();
  await expect(page.getByText(/is waiting for review/)).toBeVisible();
}

test("a candidate's deletion request: declined with a reason, then approved, which closes the account", async ({ page, browser }) => {
  const email = await candidate(page.request);
  await signIn(page, email, PASSWORD);
  await requestDeletion(page);
  await expect(page.getByRole("button", { name: "Request deletion" })).toHaveCount(0);

  const hr = await asStaff(browser, "hr.manager@edusphere.local");
  await hr.getByRole("link", { name: "Data requests" }).click();
  await expect(hr.getByRole("heading", { name: "Candidate data requests" })).toBeVisible();
  let card = hr.getByRole("listitem").filter({ hasText: email });
  await card.getByRole("button", { name: "Decline…" }).click();
  await card.getByLabel("Reason shown to the candidate").fill("Your placement contract needs these records until March");
  await card.getByRole("button", { name: "Decline the request" }).click();
  await expect(hr.getByRole("status").filter({ hasText: "request was declined" })).toBeVisible();

  await page.reload();
  await expect(page.getByText(/was declined: Your placement contract needs these records/)).toBeVisible();
  await requestDeletion(page); // asks again

  await hr.reload();
  card = hr.getByRole("listitem").filter({ hasText: email });
  await card.getByRole("button", { name: "Approve deletion" }).click();
  await card.getByRole("button", { name: "Delete the data" }).click();
  await expect(hr.getByRole("status").filter({ hasText: "data was deleted" })).toBeVisible();
  await expect(hr.getByRole("listitem").filter({ hasText: email })).toHaveCount(0);

  await page.reload(); // the candidate's session has ended (the existing access card for an unavailable user)
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await expect(page.getByRole("alert").filter({ hasText: /incorrect|invalid|not/i })).toBeVisible();
});

test("only super admin changes the retention rule; the HR Manager reads it; both pages fit a phone", async ({ browser }) => {
  const admin = await asStaff(browser, "superadmin@edusphere.local");
  await admin.goto("/it/hr-manager/data-requests");
  const rule = admin.getByRole("region", { name: "Retention rule" });
  await rule.getByLabel("Months after the last activity").fill("3");
  await rule.getByRole("button", { name: "Save rule" }).click();
  await expect(rule.getByRole("alert")).toHaveText(/from 6 to 120/);
  await rule.getByLabel("Months after the last activity").fill("36");
  await rule.getByRole("button", { name: "Save rule" }).click();
  await expect(rule.getByText("On — 36 months after the last activity")).toBeVisible();

  const hr = await asStaff(browser, "hr.manager@edusphere.local");
  await hr.setViewportSize({ width: 375, height: 800 });
  await hr.goto("/it/hr-manager/data-requests");
  const shown = hr.getByRole("region", { name: "Retention rule" });
  await expect(shown.getByText("On — 36 months after the last activity")).toBeVisible();
  await expect(shown.getByRole("button", { name: "Save rule" })).toHaveCount(0);
  expect(await noSideScroll(hr)).toBe(true);

  await rule.getByRole("button", { name: "Turn off" }).click(); // shared DB: leave the rule off
  await expect(rule.getByText("Off", { exact: true })).toBeVisible();
});

test("a recruiter records the basis when adding a candidate and the record shows it", async ({ browser }) => {
  const recruiter = await asStaff(browser, "placement@edusphere.local");
  await recruiter.goto("/recruiter/candidates/new");
  const unique = `${Date.now()}`;
  await recruiter.getByLabel(/^Name/).fill(`Basis ${unique}`);
  await recruiter.getByLabel(/^Email/).fill(`hrc035-r-${unique}@example.com`);
  await recruiter.getByLabel("Source *").selectOption({ index: 1 });
  await recruiter.getByRole("button", { name: "Add candidate" }).click();
  await expect(recruiter.getByRole("alert").filter({ hasText: "Choose why EduSphere may hold" })).toBeVisible();
  await recruiter.getByLabel(/^Basis for holding/).selectOption("provided_for_placement");
  await recruiter.getByRole("button", { name: "Add candidate" }).click();
  await recruiter.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}$/);
  await expect(recruiter.getByText("They shared their details for job placement (added by a recruiter)")).toBeVisible();
});
