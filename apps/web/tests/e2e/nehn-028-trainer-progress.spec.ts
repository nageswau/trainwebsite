import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// nehn-028 (DEC-SCOPE-308): the trainer's Student Progress page leads with one batch's students against the certificate criteria --
// attendance with an at-risk flag, assignments, assessments, progress and eligibility with its reasons. Each run registers a fresh
// student in the demo trainer's first batch and marks one present and one absent session (50%), so it can repeat on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";

async function api(browser: Browser, email: string, password = DEMO): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password, division: "it" } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", DEMO);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function atRiskLearner(browser: Browser) {
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const name = `N028 Learner ${stamp}`;
  const email = `n028-${stamp}@example.com`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: name, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  const enrolled = await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } });
  expect(enrolled.status(), await enrolled.text()).toBe(201);
  const agreement = await (await student.get("/api/v1/workflows/it/student/agreements/current")).json();
  expect((await student.post(`/api/v1/workflows/it/student/agreements/${agreement.id}/accept`)).ok()).toBeTruthy();
  const studentId = (await (await student.get("/api/v1/auth/me")).json()).id;
  for (const [day, status] of [["2001-01-01", "present"], ["2001-01-02", "absent"]]) {
    const marked = await trainer.post("/api/v1/workflows/it/trainer/attendance", { data: { batch_id: batchId, session_date: day, records: [{ student_id: studentId, status }] } });
    expect(marked.status(), await marked.text()).toBe(201);
  }
  return { name, batchId, enrollmentId: (await enrolled.json()).id as string, trainer, student };
}

test("trainer spots an at-risk student and reads why they are not eligible", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", message => message.type() === "error" && consoleErrors.push(message.text()));
  const { name, batchId, enrollmentId, trainer, student } = await atRiskLearner(browser);

  // AC1: the table's numbers are the eligibility endpoint's.
  const progress = await (await trainer.get(`/api/v1/workflows/it/batches/${batchId}/progress`)).json();
  const row = progress.students.find((item: { enrollment_id: string }) => item.enrollment_id === enrollmentId);
  const eligibility = await (await trainer.get(`/api/v1/workflows/it/certificates/eligibility/${enrollmentId}`)).json();
  expect([row.attendance_percent, row.eligible]).toEqual([eligibility.attendance_percent, eligibility.eligible]);
  expect(row.at_risk).toBe(true);
  // AC4: a student cannot read the batch's progress.
  expect((await student.get(`/api/v1/workflows/it/batches/${batchId}/progress`)).status()).toBe(403);

  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/student-progress");
  // AC3: the subtitle names what the table shows; the old progress-only table is gone.
  await expect(page.getByText("Attendance, assignments, assessments, progress and certificate eligibility for each student in your batches.")).toBeVisible();
  await expect(page.getByText("No records yet")).toHaveCount(0);

  const panel = page.locator(".trainer-progress");
  await panel.getByLabel("Search students").fill(name);
  const learner = panel.getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(name) }) }); // not its details row
  await expect(learner.getByText("50%")).toBeVisible();
  await expect(learner.getByText("At risk")).toBeVisible(); // AC2
  await expect(learner.getByText("Not eligible")).toBeVisible();
  expect(await learner.getByRole("rowheader").evaluate(cell => getComputedStyle(cell).textTransform)).toBe("none"); // QA28-02
  await learner.getByRole("button", { name: `Details for ${name}` }).click();
  const details = panel.getByRole("region", { name: `${name} progress details` });
  await expect(details.getByText("Attendance 50% (needs 75%)")).toBeVisible();
  await expect(details.getByText("Progress 0% (needs 100%)")).toBeVisible();

  await panel.getByLabel("At risk only").check();
  await expect(learner).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("the progress table fits a phone without sideways page scroll", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const { name } = await atRiskLearner(browser);
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/student-progress");
  const panel = page.locator(".trainer-progress");
  await panel.getByLabel("Search students").fill(name);
  await expect(panel.getByRole("row", { name: new RegExp(name) })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
