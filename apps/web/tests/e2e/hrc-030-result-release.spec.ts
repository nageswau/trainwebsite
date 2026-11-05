import { expect, test, type Page } from "@playwright/test";

// hrc-030 (DEC-SCOPE-409; AC1-AC3): the seeded recruiter decides the seeded IT student's Final Round as Selected (through the API: the
// interview is scheduled ahead, then moved into the past with the legacy PATCH so it can be decided at once). Until the HR Manager publishes
// it, the student's portal shows the application at Interview and no result; the recruiter's card says it waits for approval. The HR Manager
// edits the message and publishes it from "Result approvals"; then the student sees Selected and the message.

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

test("result release: a decision waits for approval, the HR Manager publishes it and only then the student sees it", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const title = `E2E Result Analyst ${stamp}`;
  const message = `Welcome aboard ${stamp} -- the team will call you.`;
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const failedCalls: string[] = [];
  page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && failedCalls.push(r.url()));

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Hrc030 ${stamp} Ltd` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title, location: "Pune" } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const requirement = (await created.json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }

  await signIn(page, STUDENT, "/it/student/dashboard");
  const applied = await page.request.post(`/api/v1/workflows/it/jobs/${requirement.id}/apply`, { data: {} });
  expect(applied.status()).toBe(201);
  const applicationId = (await applied.json()).id as string;
  const name = (await (await page.request.get("/api/v1/auth/me")).json()).full_name as string;

  // The decision (API): schedule ahead, move it into the past (legacy reschedule), Completed, then Selected on the Final Round.
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  const ahead = new Date(Date.now() + 3 * 86_400_000).toISOString();
  const scheduled = await page.request.post("/api/v1/recruiter/interviews", { data: { application_id: applicationId, round: "final_round", scheduled_at: ahead, mode: "Online", notify: false } });
  expect(scheduled.status()).toBe(201);
  const interviewId = (await scheduled.json()).interview.id as string;
  const past = new Date(Date.now() - 3_600_000).toISOString();
  expect((await page.request.patch(`/api/v1/workflows/it/interviews/${interviewId}`, { data: { scheduled_at: past } })).ok()).toBeTruthy();
  expect((await page.request.post(`/api/v1/recruiter/interviews/${interviewId}/status`, { data: { status: "completed" } })).ok()).toBeTruthy();
  const decided = await page.request.post(`/api/v1/recruiter/interviews/${interviewId}/status`, { data: { status: "selected" } });
  expect(decided.ok()).toBeTruthy();
  expect((await decided.json()).interview.result_release.state).toBe("pending_approval");

  // The recruiter's card: the candidate has not been told.
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).first().click();
  const item = candidates.getByRole("list", { name: `Interviews of ${name}` }).locator(":scope > li").first();
  await expect(item).toContainText("Result for the candidate: Selected — waiting for approval before the candidate sees it");

  // AC1: the student sees nothing yet.
  await signIn(page, STUDENT, "/it/student/dashboard");
  await page.goto("/it/student/job-applications");
  const results = page.getByRole("region", { name: "My results" });
  await expect(results).not.toContainText("Loading results…");
  await expect(results).not.toContainText(title);
  const row = page.getByRole("row").filter({ hasText: title });
  await expect(row).toContainText("Interview");
  await expect(row).not.toContainText("Selected");

  // The HR Manager publishes it with an edited message.
  await signIn(page, HR_MANAGER, "/it/hr-manager/dashboard");
  await page.getByRole("link", { name: "Result approvals" }).first().click();
  await page.waitForURL("**/it/hr-manager/results");
  await expect(page.getByRole("heading", { name: "Result approvals" })).toBeVisible();
  const card = page.getByRole("listitem").filter({ hasText: title });
  await expect(card).toContainText(`${name}`);
  await expect(card).toContainText("Final decision");
  await card.getByLabel("Message to the candidate").fill(message);
  await card.getByRole("button", { name: "Publish result" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Result published to" })).toContainText(name);
  await expect(page.getByRole("listitem").filter({ hasText: title })).toHaveCount(0);
  await page.getByRole("link", { name: /^Published \(/ }).click();
  await page.waitForURL("**/it/hr-manager/results?state=released");
  await expect(page.getByRole("listitem").filter({ hasText: title })).toContainText(message);

  // AC1/AC3: now the student sees Selected and the message.
  await signIn(page, STUDENT, "/it/student/dashboard");
  await page.goto("/it/student/job-applications");
  await expect(page.getByRole("list", { name: "My results" })).toContainText(message);
  await expect(page.getByRole("row").filter({ hasText: title })).toContainText("Selected");

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
