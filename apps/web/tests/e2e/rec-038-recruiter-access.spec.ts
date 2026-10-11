import { expect, test, type Page } from "@playwright/test";

// rec-038 (DEC-SCOPE-185 RM7): the recruiter CRM's permission matrix as the browser sees it. Roles outside the CRM (it_admin,
// overseas_admin, IT student) get "Access unavailable" on the recruiter pages; hr_team too, except the candidate pool it reads (R11, Q-28);
// signed out is sent to the IT sign-in; the company's assigned BDM reads the company with no edit control (R10); a recruiter opening
// another recruiter's company reads it as missing (RM4). The refusal card fits a phone.

const DEMO = "Demo@123";
// The company page's write controls: super_admin gets every one; the assigned BDM (R10, read-only) gets none.
const WRITE_CONTROLS = ["Edit", "Archive", "Add contact", "Log call", "Add follow-up", "Schedule meeting", "Start contract"];
const RECRUITER_PAGES =["/recruiter/companies", "/recruiter/requirements", "/recruiter/manager/team"];

async function signIn(page: Page, loginPath: string, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", DEMO);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function expectRefused(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Access unavailable" }), path).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to your dashboard" }), path).toBeVisible();
}

for (const [loginPath, email] of [
  ["/it/login", "itadmin@edusphere.local"],
  ["/overseas/login", "overseasadmin@edusphere.local"],
  ["/it/login", "student.it@edusphere.local"],
] as const) {
  test(`${email} is refused on every recruiter page`, async ({ page }) => {
    await signIn(page, loginPath, email);
    for (const path of [...RECRUITER_PAGES, "/recruiter/candidates"]) await expectRefused(page, path);
  });
}

test("hr_team reads the candidate pool and is refused the rest of the CRM", async ({ page }) => {
  await signIn(page, "/it/login", "hr@edusphere.local");
  for (const path of RECRUITER_PAGES) await expectRefused(page, path);
  await page.goto("/recruiter/candidates");
  await expect(page.getByRole("heading", { name: "Candidates", exact: true })).toBeVisible();
  await expect(page.getByText("You can view candidates and download resumes.")).toBeVisible();
  await expect(page.getByRole("link", { name: "+ Add candidate" })).toHaveCount(0); // R11: hr_team reads, never writes
});

test("signed out, a recruiter page sends you to the IT sign-in", async ({ page }) => {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/recruiter/companies");
  await expect(page).toHaveURL(/\/it\/login/);
});

test("the assigned BDM reads the company without an edit control; another recruiter reads it as missing", async ({ page }) => {
  const name = `E2E R38 Linked ${Date.now()}`;
  await signIn(page, "/it/login", "bdm.college@edusphere.local");
  const bdm = await (await page.request.get("/api/v1/auth/me")).json();
  await signIn(page, "/admin/login", "superadmin@edusphere.local");
  const created = await page.request.post("/api/v1/recruiter/companies", { data: { name, assigned_bdm_user_id: bdm.id } });
  expect(created.ok(), await created.text()).toBe(true);
  const { company } = await created.json();
  await page.goto(`/recruiter/companies/${company.id}`);
  for (const control of WRITE_CONTROLS) await expect(page.getByRole("button", { name: control, exact: true })).toBeVisible();

  await signIn(page, "/it/login", "bdm.college@edusphere.local");
  await page.goto("/recruiter/companies");
  await expect(page.getByRole("heading", { name: "Companies you are linked to" })).toBeVisible();
  await page.goto(`/recruiter/companies/${company.id}`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Contacts", exact: true })).toBeVisible();
  for (const control of WRITE_CONTROLS) await expect(page.getByRole("button", { name: control, exact: true })).toHaveCount(0);

  // The company has no recruiter (created by super_admin), so the seeded recruiter is out of its scope: it reads as missing.
  await signIn(page, "/it/login", "placement@edusphere.local");
  await page.goto(`/recruiter/companies/${company.id}`);
  await expect(page.getByText("Company not found")).toBeVisible();
});

test("the refusal card fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "/it/login", "itadmin@edusphere.local");
  await expectRefused(page, "/recruiter/companies");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
