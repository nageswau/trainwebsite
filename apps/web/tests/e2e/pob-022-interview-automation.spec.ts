import { expect, test, type Page } from "@playwright/test";

// pob-022 (DEC-SCOPE-421 A1/A2/A9): the Team Lead adds an approved interview confirmation template and tunes the automation settings on
// /recruiter/interviews; the recruiter schedules an interview choosing that template (the request carries it and the notice summary comes
// back). The reminder and chase sweeps run in the worker and are asserted in test_pob_022_interview_automation.py.

/** IT accounts sign in at /it/login; a global one (the placement manager) at /admin/login. Waits until the page has left the login form. */
async function signIn(page: Page, email: string, login = "/it/login") {
  await page.context().clearCookies();
  await page.goto(login);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

function istInput(days: number, minute: number): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000));
  return `${day}T11:${String(minute).padStart(2, "0")}`;
}

const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const STUDENT = "student.it@edusphere.local";
const DEFAULTS = { first_reminder_hours: 24, second_reminder_hours: 2, reminder_template_id: null, chase_after_hours: 24, escalate_after_hours: 24, chase_template_id: null };

test("interview automation: settings for the Team Lead, the confirmation template in the scheduler", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const failedCalls: string[] = [];
  page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && failedCalls.push(r.url()));

  // The Team Lead: an approved shared confirmation template, and the settings panel.
  await signIn(page, MANAGER, "/admin/login");
  const templateName = `E2E Confirmation ${stamp}`;
  const created = await page.request.post("/api/v1/recruiter/templates", { data: {
    channel: "email", kind: "interview_confirmation", name: templateName, subject: "Your interview for {job_title}",
    body: "Hello {name}, your interview is on {interview_date} at {interview_time}.", category: "candidate" } });
  expect(created.status(), await created.text()).toBe(201);
  await page.goto("/recruiter/interviews");
  const panel = page.getByRole("form", { name: "Interview automation" });
  await expect(panel.getByLabel("First reminder (hours before)")).toHaveValue(/\d+/);
  await panel.getByLabel("Chase client feedback after (hours)").fill("48");
  await panel.getByRole("button", { name: "Save automation" }).click();
  await expect(page.getByText("Interview automation saved.")).toBeVisible();
  await panel.getByLabel("Second reminder (hours before)").fill("30");
  await panel.getByRole("button", { name: "Save automation" }).click();
  await expect(page.getByText("The second reminder must come closer to the interview than the first")).toBeVisible();
  expect((await page.request.put("/api/v1/recruiter/interview-automation/settings", { data: DEFAULTS })).ok()).toBeTruthy();

  // A requirement the student applies to.
  await signIn(page, RECRUITER);
  await page.goto("/recruiter/interviews");
  await expect(page.getByRole("form", { name: "Interview automation" })).toHaveCount(0); // not the recruiter's
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Pob022 ${stamp} Ltd` } });
  const requirement = (await (await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `E2E Auto ${stamp}`, location: "Pune" } })).json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }
  await signIn(page, STUDENT);
  expect((await page.request.post(`/api/v1/workflows/it/jobs/${requirement.id}/apply`, { data: {} })).status()).toBe(201);
  const name = (await (await page.request.get("/api/v1/auth/me")).json()).full_name as string;

  // The recruiter schedules with the template.
  await signIn(page, RECRUITER);
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).first().click();
  await candidates.getByRole("button", { name: `+ Schedule interview for ${name}` }).click();
  const form = candidates.getByRole("form", { name: "Schedule interview" });
  await form.getByLabel("Round (required)").selectOption({ label: "HR Round" });
  await form.getByLabel("Date and time (IST, required)").fill(istInput(5, stamp % 60));
  const select = form.getByLabel("Confirmation message");
  await expect(select).toBeEnabled();
  await select.selectOption({ label: templateName });
  const [request] = await Promise.all([
    page.waitForRequest((r) => r.url().endsWith("/api/v1/recruiter/interviews") && r.method() === "POST"),
    form.getByRole("button", { name: "Schedule interview" }).click(),
  ]);
  expect(request.postDataJSON().template_id).toBe((await created.json()).id);
  await expect(page.getByText(`HR Round scheduled for ${name}. Candidate: notified in the portal.`)).toBeVisible();

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("status of 422"))).toEqual([]); // the refused save above is a deliberate 422
});
