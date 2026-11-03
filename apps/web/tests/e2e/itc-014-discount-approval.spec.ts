import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-014 (DEC-SCOPE-363): a fresh IT student enrols (a 45,000-style bill); a throwaway IT counselor linked to them requests a discount on
// the student record -- the fee does not change while it waits (AC1); the IT Admin approves it on the Payments page and the student
// record shows the lower balance and the approved discount (AC2). The IT Admin's own request shows no buttons and the API refuses
// self-approval (AC3). Unique per run, so it repeats on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";

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

const inr = (n: number) => `INR ${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

async function linkedLearner(browser: Browser) {
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const email = `i014-${stamp}@example.com`;
  const name = `I014 Learner ${stamp}`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: name, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const [account] = (await (await student.get("/api/v1/it/student/fee-accounts")).json()) as { enrollment_id: string; balance: number }[];
  const me = (await (await student.get("/api/v1/auth/me")).json()) as { id: string };
  const admin = await api(browser, "itadmin@edusphere.local");
  const created = await admin.post("/api/v1/admin/users", { data: { role: "counselor", division: "it", full_name: `I014 Counselor ${stamp}`, email: `i014-c-${stamp}@example.local` } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const counselor = (await created.json()) as { id: string; email: string; development_welcome_token: string };
  await activateWithToken(admin, counselor.development_welcome_token);
  const assigned = await admin.put(`/api/v1/admin/it/students/${me.id}/counselor`, { data: { counselor_id: counselor.id, reason: "itc-014 e2e" } });
  expect(assigned.ok(), await assigned.text()).toBeTruthy();
  return { name, studentId: me.id, enrollmentId: account.enrollment_id, balance: account.balance, counselorEmail: counselor.email, admin };
}

test("a counselor's discount request waits for the IT Admin's approval, which lowers the balance", async ({ browser, page }) => {
  test.setTimeout(150_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const { name, studentId, enrollmentId, balance, counselorEmail, admin } = await linkedLearner(browser);
  expect(balance).toBeGreaterThan(1000);

  // The counselor requests 1,000 off on the student record; the balance is unchanged (AC1).
  await signIn(page, counselorEmail, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/students/${studentId}/profile`);
  const fees = page.locator("section", { has: page.getByRole("heading", { name: "Fees and reminders" }) });
  await expect(fees.getByText("No discount has been requested yet.")).toBeVisible();
  await fees.getByLabel(/Discount amount/).fill(String(balance + 1));
  await fees.getByLabel("Reason").fill("Sibling discount");
  await fees.getByRole("button", { name: "Request discount" }).click();
  await expect(fees.locator(".form-error[role=alert]")).toContainText(`no more than ${inr(balance)}`);
  await fees.getByLabel(/Discount amount/).fill("1000");
  await fees.getByRole("button", { name: "Request discount" }).click();
  await expect(fees.getByRole("status").filter({ hasText: "Discount requested." })).toBeVisible();
  await expect(fees.getByRole("list", { name: "Discount requests" }).getByText("Waiting for approval")).toBeVisible();
  await expect(fees.getByRole("button", { name: "Request discount" })).toHaveCount(0);
  const unchanged = (await (await admin.get(`/api/v1/it/enrollments/${enrollmentId}/fee-account`)).json()) as { balance: number; discount_approved: number };
  expect([unchanged.balance, unchanged.discount_approved]).toEqual([balance, 0]);

  // The IT Admin approves it on the Payments page (AC2).
  await page.context().clearCookies();
  await signIn(page, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
  await page.goto("/it/admin/payments");
  const queue = page.locator("section", { has: page.getByRole("heading", { name: "Discount approvals" }) });
  const item = queue.getByRole("listitem").filter({ hasText: name });
  await expect(item).toContainText(`${inr(1000)} off · Sibling discount`);
  await item.getByRole("button", { name: `Approve discount for ${name}` }).click();
  await expect(queue.getByRole("status")).toHaveText(`Discount approved for ${name}. The fee balance is updated.`);
  await expect(item).toHaveCount(0);

  await page.goto(`/it/admin/students/${studentId}/profile`);
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Fees and reminders" }) });
  await expect(card.getByRole("list", { name: "Discount requests" }).getByText("Approved", { exact: true })).toBeVisible();
  await expect(card).toContainText(inr(balance - 1000));

  // The IT Admin's own request: no buttons in the queue, and the API refuses self-approval (AC3).
  const own = await admin.post(`/api/v1/it/enrollments/${enrollmentId}/discount-requests`, { data: { amount: 500, reason: "Early bird" } });
  expect(own.status()).toBe(201);
  const ownId = ((await own.json()) as { id: string }).id;
  await page.goto("/it/admin/payments");
  const mine = queue.getByRole("listitem").filter({ hasText: name });
  await expect(mine).toContainText("Your request — another approver must decide it.");
  await expect(mine.getByRole("button")).toHaveCount(0);
  expect((await admin.post(`/api/v1/it/discount-requests/${ownId}/approve`, { data: {} })).status()).toBe(403);
  expect(consoleErrors).toEqual([]);
});

test("only a discounts.approve holder reads the queue", async ({ browser }) => {
  const trainer = await api(browser, "trainer@edusphere.local");
  expect((await trainer.get("/api/v1/it/discount-requests")).status()).toBe(403);
  const student = await api(browser, "student.it@edusphere.local");
  expect((await student.get("/api/v1/it/discount-requests")).status()).toBe(403);
});
