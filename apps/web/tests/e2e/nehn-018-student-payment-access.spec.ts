import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// nehn-018 (DEC-SCOPE-304): an enrolled-but-unpaid student sees course and fees, and the gated sections locked with "Complete payment to
// unlock" (AC1); the IT admin's policy change applies on the student's next page (AC4); a fee discounted to nothing counts as paid.
// Each run registers a fresh student and enrols them in the demo trainer's batch (billed, unpaid), so it repeats on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
const RULES = "/api/v1/workflows/it/student-access/rules";

async function api(browser: Browser, email: string, password = DEMO): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password, division: "it" } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function unpaidLearner(browser: Browser): Promise<{ email: string; student: APIRequestContext }> {
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const email = `n018-${stamp}@example.com`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: `N018 Learner ${stamp}`, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  return { email, student };
}

test("an unpaid student sees locked sections; the admin's policy and a full discount unlock them", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const { email, student } = await unpaidLearner(browser);
  const admin = await api(browser, "itadmin@edusphere.local");
  const original = (await (await admin.get(RULES)).json()) as { rules: { feature: string; min_state: string }[] };
  const restore = Object.fromEntries(original.rules.map((r) => [r.feature, r.min_state]));

  try {
    // AC1: locked, not hidden; the call to action goes to Fees; course information stays open.
    await signIn(page, email, STUDENT_PASSWORD, "/it/student/dashboard");
    await page.goto("/it/student/attendance");
    await expect(page.getByRole("heading", { name: "Attendance is locked" })).toBeVisible();
    await expect(page.locator(".portal-nav").getByRole("link", { name: "Attendance Locked" })).toBeVisible();
    await page.getByRole("link", { name: "Complete payment to unlock" }).click();
    await page.waitForURL("**/it/student/fees");
    await expect(page.getByRole("heading", { level: 2, name: "Fee Status" })).toBeVisible();
    await page.goto("/it/student/course");
    await expect(page.getByRole("heading", { name: "Live classes is locked" })).toBeVisible();
    const refused = await student.get("/api/v1/workflows/it/student/attendance");
    expect(refused.status()).toBe(403);
    expect((await refused.json()).detail).toMatchObject({ code: "payment_required", feature: "attendance", current_state: "enrolled_pending_payment" });

    // AC4: the IT admin opens attendance at enrolment, on the Payments page; the student's next page has it.
    const adminContext = await browser.newContext();
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
    await adminPage.goto("/it/admin/payments");
    const card = adminPage.locator(".action-card", { has: adminPage.getByRole("heading", { name: "Student access by payment" }) });
    await card.getByLabel("Attendance").selectOption("enrolled_pending_payment");
    await card.getByRole("button", { name: "Save access rules" }).click();
    await expect(card.getByRole("status")).toHaveText("Access rules saved. Students see the change on their next page.");
    await adminContext.close();
    await page.goto("/it/student/attendance");
    await expect(page.getByRole("heading", { level: 2, name: "Attendance & Progress" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Attendance is locked" })).toHaveCount(0);
    await expect(page.locator(".portal-nav").getByRole("link", { name: "Attendance", exact: true })).toBeVisible();

    // A fee discounted to nothing is paid: every feature opens, without signing in again.
    const fees = (await (await student.get("/api/v1/payments/mine")).json()) as { id: string; status: string }[];
    for (const fee of fees.filter((f) => f.status === "pending")) {
      expect((await admin.post(`/api/v1/admin/payments/${fee.id}/discount`, { data: { amount: 0, reason: "nehn-018 e2e scholarship" } })).ok()).toBeTruthy();
    }
    await page.goto("/it/student/assignments");
    await expect(page.getByRole("heading", { name: /is locked$/ })).toHaveCount(0);
    await expect(page.locator(".portal-nav .nav-locked")).toHaveCount(0);
    expect((await (await student.get("/api/v1/workflows/it/student/access")).json()).state).toBe("fully_paid");
    expect(consoleErrors).toEqual([]);
  } finally {
    expect((await admin.put(RULES, { data: { rules: restore } })).ok()).toBeTruthy();
  }
});

test("only the IT admin's grant reads or changes the policy", async ({ browser }) => {
  for (const email of ["student.it@edusphere.local", "trainer@edusphere.local", "coordinator@edusphere.local"]) {
    expect((await (await api(browser, email)).get(RULES)).status()).toBe(403);
  }
  const anonymous = await browser.newContext();
  expect((await anonymous.request.get(RULES)).status()).toBe(401);
});

test("the seeded student, who has paid a first instalment, keeps every section", async ({ page }) => {
  await signIn(page, "student.it@edusphere.local", DEMO, "/it/student/dashboard");
  await page.goto("/it/student/assignments");
  await expect(page.getByRole("heading", { level: 2, name: "Assignments" })).toBeVisible();
  await expect(page.locator(".portal-nav .nav-locked")).toHaveCount(0);
});
