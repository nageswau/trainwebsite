import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-013 (DEC-SCOPE-344): an enrolled IT student owes the course fee; the IT Admin records a part payment (UPI, with its reference) and
// then the rest (cash) on the Payments page; the balance follows each payment on the Enrolments page and on the student's Fees page,
// whose paid fee cards name their mode and reference. A fresh student per run, so it repeats on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
type Account = { enrollment_id: string; balance: number; total_payable: number; state: string };

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

async function enrolledLearner(browser: Browser) {
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const email = `i013-${stamp}@example.com`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: `I013 Learner ${stamp}`, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const [account] = (await (await student.get("/api/v1/it/student/fee-accounts")).json()) as Account[];
  return { email, student, account };
}

async function record(page: Page, enrollmentId: string, amount: number, mode: string, reference?: string) {
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Record enrolment payment" }) });
  await form.getByLabel("Enrolment reference").fill(enrollmentId);
  await form.getByLabel("Amount paid").fill(String(amount));
  await form.getByLabel("Payment mode").selectOption({ label: mode });
  if (reference) await form.getByLabel("Transaction reference").fill(reference);
  await form.getByRole("button", { name: "Record enrolment payment" }).click();
  return form;
}

const inr = (value: number) => `INR ${value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

test("part and full payments update the fee account for the admin and the student", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const { email, account } = await enrolledLearner(browser);
  expect(account.state).toBe("enrolled_pending_payment");
  const fee = account.total_payable;
  const part = Math.floor(fee / 2) + 0.5; // QA13-01: rupees and paise

  await signIn(page, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
  await page.goto("/it/admin/payments");
  // Q-13: more than is owed is refused and changes nothing
  let form = await record(page, account.enrollment_id, fee + 1, "Cash");
  await expect(form.getByRole("alert")).toContainText("Record at most");
  form = await record(page, account.enrollment_id, part, "UPI", "UPI-E2E-1");
  await expect(form.getByRole("status")).toHaveText(`Payment recorded. Remaining balance ${inr(fee - part)}.`);

  await page.goto("/it/admin/enrollments");
  const row = page.locator("tr", { has: page.getByRole("cell", { name: account.enrollment_id, exact: true }) });
  await expect(row).toContainText(inr(fee - part));
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, email, STUDENT_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/fees");
  const card = page.getByLabel(/^Fee account for /);
  await expect(card).toContainText("Partially paid");
  await expect(card.getByText("Balance").locator("xpath=following-sibling::dd")).toHaveText(inr(fee - part));
  await expect(page.getByText("Paid by UPI · Ref UPI-E2E-1")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
  await page.goto("/it/admin/payments");
  form = await record(page, account.enrollment_id, fee - part, "Cash");
  await expect(form.getByRole("status")).toHaveText(`Payment recorded. Remaining balance ${inr(0)}.`);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, email, STUDENT_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/fees");
  await expect(page.getByLabel(/^Fee account for /)).toContainText("Fully paid");
  await expect(page.getByText("Paid by Cash")).toBeVisible();
  // the only console error is the browser's log of the deliberate over-amount refusal above
  expect(consoleErrors.filter((text) => !text.includes("status of 422"))).toEqual([]);
});
