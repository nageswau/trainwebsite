import { expect, test, type Page } from "@playwright/test";

// hrc-032 (DEC-SCOPE-412; AC1, AC3): a student applies, and the recruiter who owns the vacancy reads "New application" on their new Notifications
// page; the HR Manager's Delivery exceptions page answers, filters and refuses a recruiter. A failed delivery cannot be produced from the UI here
// (no worker runs in this stack), so the retry itself is covered by test_hrc_032_exceptions.py and vitest.

async function signIn(page: Page, email: string, landing: string, password = "Demo@123") {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const STUDENT = "student.it@edusphere.local";
const HR_MANAGER = "hr.manager@edusphere.local";

test("a student's application reaches the owner's Notifications page once", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Hrc032 ${stamp} Ltd` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `E2E Notice Analyst ${stamp}`, location: "Pune" } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const requirement = (await created.json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }

  await signIn(page, STUDENT, "/it/student/dashboard");
  const applied = await page.request.post(`/api/v1/workflows/it/jobs/${requirement.id}/apply`, { data: {} });
  expect(applied.status()).toBe(201);

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.getByRole("link", { name: "Notifications" }).first().click();
  await page.waitForURL("**/recruiter/notifications");
  await page.getByLabel("Type").selectOption({ label: "New application" });
  const open = page.getByRole("listitem").filter({ has: page.locator(`a[href="/recruiter/requirements/${requirement.id}"]`) });
  await expect(open).toHaveCount(1);
  await expect(open).toContainText("A candidate applied to a vacancy you own");
});

test("the HR Manager reads Delivery exceptions and can filter it; a recruiter is refused", async ({ page }) => {
  test.setTimeout(240_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.getByRole("link", { name: "Delivery exceptions" }).first().click();
  await page.waitForURL("**/recruiter/notification-exceptions");
  await expect(page.getByRole("heading", { name: "Delivery exceptions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Failed deliveries \(\d+\)$/ })).toBeVisible();

  await page.getByLabel("Channel").selectOption("sms");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await page.waitForURL("**/recruiter/notification-exceptions?*channel=sms*");
  await expect(page.getByRole("link", { name: "Clear filters" })).toBeVisible();
  await expect(page.getByLabel("Channel")).toHaveValue("sms");
  expect(consoleErrors).toEqual([]);

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/notification-exceptions");
  await expect(page.getByText("You cannot handle failed notifications")).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Failed deliveries/ })).toHaveCount(0);
});
