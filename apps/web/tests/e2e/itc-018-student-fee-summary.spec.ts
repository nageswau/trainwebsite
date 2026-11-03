import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-018 (DEC-SCOPE-353): a fresh IT student enrols (one pending fee), the IT Admin records a part payment, and the student's Fees page
// shows the balance and the next amount due; the Course page lists the batch's dates, mode and room or link; another student cannot
// download the receipt (404). A fresh student per run, so it repeats on one database.

const DEMO = "Demo@123";
const PASSWORD = "Sup3r-Secret-Pass!";
type Account = { enrollment_id: string; balance: number; total_payable: number; next_due: { amount: number; due_date: string | null } | null };

async function api(browser: Browser, email: string, password = DEMO): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password, division: "it" } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function learner(browser: Browser, tag: string) {
  const stamp = `${Date.now()}-${tag}`;
  const email = `i018-${stamp}@example.com`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: PASSWORD, full_name: `I018 Learner ${stamp}`, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  return { email, request: await api(browser, email, PASSWORD) };
}

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
}

const inr = (value: number) => `INR ${value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

test("the student sees the balance, the next due and the course details; another student gets 404 on the receipt", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const { email, request: student } = await learner(browser, "a");
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const [before] = (await (await student.get("/api/v1/it/student/fee-accounts")).json()) as Account[];
  expect(before.next_due?.amount).toBe(before.total_payable);

  const admin = await api(browser, "itadmin@edusphere.local");
  const part = Math.floor(before.total_payable / 2);
  const recorded = await admin.post(`/api/v1/it/enrollments/${before.enrollment_id}/payments`, { data: { amount: part, payment_mode: "cash" } });
  expect(recorded.status(), await recorded.text()).toBe(201);
  const paymentId = ((await recorded.json()) as { payment: { id: string } }).payment.id;
  const rest = before.total_payable - part;

  await signIn(page, email);
  await page.goto("/it/student/fees");
  const card = page.getByLabel(/^Fee account for /);
  await expect(card.getByText("Balance").locator("xpath=following-sibling::dd")).toHaveText(inr(rest));
  await expect(card.getByText("Next due").locator("xpath=following-sibling::dd")).toContainText(inr(rest));

  await page.goto("/it/student/course");
  for (const header of ["Starts", "Ends", "Mode", "Room or link"]) await expect(page.getByRole("columnheader", { name: header })).toBeVisible();
  expect(await page.locator("table").first().innerText()).not.toMatch(/https?:\/\//);

  expect((await student.get(`/api/v1/payments/${paymentId}/receipt`)).status()).toBe(200);
  const { request: stranger } = await learner(browser, "b");
  expect((await stranger.get(`/api/v1/payments/${paymentId}/receipt`)).status()).toBe(404);
  expect(consoleErrors).toEqual([]);
});
