import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-031 (DEC-SCOPE-358): a fresh IT learner enrols (Fee pending); the IT Admin records a part payment (Partially paid) and then the
// rest (Paid) -- each move appears on the student record's lifecycle card with its history, actor and cause (AC1, AC2, the "+" case).
// A derived stage cannot be set by hand (Placed -> 409, the "-" case); the IT Admin sets Closed with a reason and clears it again. The
// student sees their stage on their own record. A fresh student per run, so it repeats on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
type Account = { enrollment_id: string; balance: number };

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

test("the lifecycle follows the fee records, keeps its history and takes only Not placed / Closed by hand", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const email = `i031-${stamp}@example.com`;
  const anon = await browser.newContext();
  const registered = await anon.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: `I031 Learner ${stamp}`, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const studentId = ((await (await student.get("/api/v1/auth/me")).json()) as { id: string }).id;
  const [account] = (await (await student.get("/api/v1/it/student/fee-accounts")).json()) as Account[];
  const admin = await api(browser, "itadmin@edusphere.local");
  const pay = (amount: number) => admin.post(`/api/v1/it/enrollments/${account.enrollment_id}/payments`, { data: { amount, payment_mode: "cash" } });

  await signIn(page, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
  const record = `/it/admin/students/${studentId}/profile`;
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Lifecycle" }) });
  await page.goto(record);
  await expect(card.getByTestId("lifecycle-stage")).toHaveText("Fee pending");
  await card.getByText(/^History/).click();
  await expect(card.getByRole("list", { name: /^Lifecycle history/ })).toContainText("Fee pending · Enrolment change");

  // AC1: a part payment, then the final one -- Partially paid -> Paid, each with the IT Admin as the actor (AC2)
  expect((await pay(1000)).status()).toBe(201);
  await page.reload();
  await expect(card.getByTestId("lifecycle-stage")).toHaveText("Partially paid");
  expect((await pay(account.balance - 1000)).status()).toBe(201);
  await page.reload();
  await expect(card.getByTestId("lifecycle-stage")).toHaveText("Paid");
  await card.getByText(/^History/).click();
  await expect(card.getByRole("list", { name: /^Lifecycle history/ })).toContainText("Partially paid → Paid · Fee payment · ");
  await expect(page.getByRole("table", { name: "Enrolments" })).toContainText("Paid");

  // "-": a derived stage cannot be set by hand
  const placed = await admin.put(`/api/v1/admin/it/students/${studentId}/enrollments/${account.enrollment_id}/lifecycle-override`, { data: { stage: "placed", reason: "Joined" } });
  expect(placed.status()).toBe(409);

  // the IT Admin closes the enrolment with a reason, then clears it
  await card.getByLabel("Set by hand").selectOption("closed");
  await card.getByLabel("Reason").fill("Moved to another city");
  await card.getByRole("button", { name: "Save stage" }).click();
  await expect(card.getByText("Stage saved.")).toBeVisible();
  await expect(card.getByTestId("lifecycle-stage")).toHaveText("Closed");
  await expect(card.getByTestId("lifecycle-override")).toContainText("Moved to another city");
  await page.reload();
  await expect(card.getByTestId("lifecycle-stage")).toHaveText("Closed");
  await card.getByRole("button", { name: "Clear hand-set stage" }).click();
  await expect(card.getByText("Hand-set stage cleared.")).toBeVisible();
  await expect(card.getByTestId("lifecycle-stage")).toHaveText("Paid");
  await page.request.post("/api/v1/auth/logout");

  // the student sees their own stage (no history, no override control)
  await signIn(page, email, STUDENT_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/profile");
  await expect(page.getByRole("table", { name: "Enrolments" })).toContainText("Paid");
  await expect(page.getByRole("heading", { name: "Lifecycle" })).toHaveCount(0);
});
