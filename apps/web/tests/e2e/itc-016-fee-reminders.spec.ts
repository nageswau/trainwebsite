import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-016 (DEC-SCOPE-357): an enrolled IT student's fee is split into a past-due installment and a later one; the student's fee summary
// badges the first Overdue (derived, IST) and the second Due, with no reminder yet (the 08:30 IST job sends them); the IT Admin sees the
// same card on the student record and edits the reminder schedule on the Payments page (invalid input refused, saved value kept on
// refresh, restored after). A fresh student per run, so it repeats on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
const SETTINGS = "/api/v1/admin/it/fee-reminder-settings";

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

const isoDay = (offset: number) => new Date(Date.now() + 5.5 * 3600_000 + offset * 86_400_000).toISOString().slice(0, 10); // IST

async function learnerWithInstallments(browser: Browser) {
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const email = `i016-${stamp}@example.com`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: `I016 Learner ${stamp}`, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const [account] = (await (await student.get("/api/v1/it/student/fee-accounts")).json()) as { enrollment_id: string; total_payable: number }[];
  const me = (await (await student.get("/api/v1/auth/me")).json()) as { id: string };
  const admin = await api(browser, "itadmin@edusphere.local");
  // the enrolment bill is paid off by the admin and replaced by two dated installments of the same enrolment
  expect((await admin.post(`/api/v1/it/enrollments/${account.enrollment_id}/payments`, { data: { amount: account.total_payable, payment_mode: "cash" } })).status()).toBe(201);
  for (const [amount, due] of [[1500, isoDay(-2)], [2500, isoDay(10)]] as const) {
    const created = await admin.post("/api/v1/admin/payments", { data: { user_id: me.id, reference_type: "enrollment_fee", reference_id: account.enrollment_id, amount, due_date: due, provider: "manual" } });
    expect(created.ok(), await created.text()).toBeTruthy();
  }
  return { email, studentId: me.id, admin };
}

test("installments are badged overdue or due, and the IT Admin edits the reminder schedule", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const { email, studentId, admin } = await learnerWithInstallments(browser);
  const original = await (await admin.get(SETTINGS)).json();

  await signIn(page, email, STUDENT_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/fees");
  const items = page.getByRole("list", { name: "Installments" }).getByRole("listitem");
  const late = items.filter({ hasText: "INR 1,500.00" });
  await expect(late.getByText("Overdue", { exact: true })).toBeVisible();
  await expect(late).toContainText("No reminder sent yet");
  await expect(items.filter({ hasText: "INR 2,500.00" }).getByText("Due", { exact: true })).toBeVisible();
  await expect(items.filter({ hasText: "Paid" }).first()).toBeVisible();

  await page.context().clearCookies();
  await signIn(page, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
  await page.goto(`/it/admin/students/${studentId}/profile`);
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Fees and reminders" }) });
  await expect(card.getByRole("list", { name: "Installments" }).getByText("Overdue", { exact: true })).toBeVisible();

  await page.goto("/it/admin/payments");
  const panel = page.locator("section", { has: page.getByRole("heading", { name: "Fee reminders" }) });
  await panel.getByLabel("Days after the due date").fill("0, 5");
  await panel.getByRole("button", { name: "Update reminder schedule" }).click();
  await expect(panel.getByRole("alert")).toHaveText("Enter up to 6 whole numbers from 1 to 90, separated by commas.");
  await panel.getByLabel("Days before the due date").fill("2");
  await panel.getByLabel("Days after the due date").fill("5, 1");
  await panel.getByRole("button", { name: "Update reminder schedule" }).click();
  await expect(panel.getByRole("status")).toHaveText("Reminder schedule saved. It applies from the next daily run.");
  await page.reload();
  await expect(panel.getByLabel("Days after the due date")).toHaveValue("1, 5");
  await expect(panel.getByText("Now: 2 days before the due date and 1 and 5 days after it.")).toBeVisible();
  expect((await admin.put(SETTINGS, { data: original })).ok()).toBeTruthy();
  expect(consoleErrors).toEqual([]);
});

test("only the IT Admin reads the reminder schedule", async ({ browser }) => {
  const trainer = await api(browser, "trainer@edusphere.local");
  expect((await trainer.get(SETTINGS)).status()).toBe(403);
  expect((await trainer.put(SETTINGS, { data: { days_before: 1, overdue_days: [] } })).status()).toBe(403);
  const student = await api(browser, "student.it@edusphere.local");
  expect((await student.get(SETTINGS)).status()).toBe(403);
});
