import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-015 (DEC-SCOPE-363): the IT Admin corrects a mistyped payment, then — once the fee is paid — records a credit note (a batch change)
// and refunds that credit; the student sees the refunded figure, the adjustments and downloads the refund receipt. A fresh student per run.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
type Account = { enrollment_id: string; balance: number; total_payable: number; next_due: { amount: number } | null };

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

const inr = (value: number) => `INR ${value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
const form = (page: Page, title: string) => page.locator(".action-card", { has: page.getByRole("heading", { name: title }) });

test("a correction, a credit note and its refund reach the student's fee account", async ({ browser, page }) => {
  test.setTimeout(150_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const email = `i015-${Date.now()}@example.com`;
  const registered = await (await browser.newContext()).request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: "I015 Learner", division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const account = async () => ((await (await student.get("/api/v1/it/student/fee-accounts")).json()) as Account[])[0];
  const { enrollment_id: eid, total_payable: fee } = await account();

  await signIn(page, "itadmin@edusphere.local", DEMO, "/it/admin/dashboard");
  await page.goto("/it/admin/payments");
  const record = async (amount: number, mode: string, reference: string) => {
    const f = form(page, "Record enrolment payment");
    await f.getByLabel("Enrolment reference").fill(eid);
    await f.getByLabel("Amount paid").fill(String(amount));
    await f.getByLabel("Payment mode").selectOption({ label: mode });
    await f.getByLabel("Transaction reference").fill(reference);
    await f.getByRole("button", { name: "Record enrolment payment" }).click();
    await expect(f.getByRole("status")).toContainText("Payment recorded.");
  };
  await record(fee, "Cash", "TYPO-1"); // mistyped: it was a UPI payment
  const [typo] = ((await (await student.get("/api/v1/payments/mine")).json()) as { id: string; status: string }[]).filter((p) => p.status === "paid");

  const correction = form(page, "Correct a recorded payment");
  await correction.getByLabel("Enrolment reference").fill(eid);
  await correction.getByLabel("Payment reference to correct").fill(typo.id);
  await correction.getByLabel("Correct amount").fill(String(fee));
  await correction.getByLabel("Correct payment mode").selectOption({ label: "UPI" });
  await correction.getByLabel("Correct transaction reference").fill("UPI-REAL-1");
  await correction.getByLabel("Reason for the correction").fill("Recorded as cash by mistake");
  await correction.getByRole("button", { name: "Correct a recorded payment" }).click();
  await expect(correction.getByRole("status")).toHaveText(`Payment corrected. Remaining balance ${inr(0)}.`);

  const adjustment = form(page, "Record fee adjustment");
  const adjust = async (kind: string, amount: number, mode?: string) => {
    await adjustment.getByLabel("Enrolment reference").fill(eid);
    await adjustment.getByLabel("Adjustment type").selectOption({ label: kind });
    await adjustment.getByLabel("Adjustment amount").fill(String(amount));
    await adjustment.getByLabel("Reason (shown to the student)").fill("Moved to the weekend batch");
    if (mode) await adjustment.getByLabel("Refunded by (refunds only)").selectOption({ label: mode });
    await adjustment.getByRole("button", { name: "Record fee adjustment" }).click();
  };
  await adjust("Credit note", 5000);
  await expect(adjustment.getByRole("status")).toContainText(`Credit on the account ${inr(5000)}.`);
  await adjust("Refund", 5000.01, "Bank transfer"); // never more than the credit
  await expect(adjustment.locator(".form-error[role=alert]")).toContainText(`Refund at most ${inr(5000)}`);
  await adjust("Refund", 5000, "Bank transfer");
  await expect(adjustment.getByRole("status")).toContainText(`Remaining balance ${inr(0)}.`);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, email, STUDENT_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/fees");
  const card = page.getByLabel(/^Fee account for /);
  await expect(card.getByText("Refunded").locator("xpath=following-sibling::dd")).toHaveText(inr(5000));
  const list = card.getByRole("list", { name: "Credits and refunds" });
  await expect(list).toContainText("Payment corrected");
  await expect(list).toContainText(`Refund · ${inr(5000)}`);
  await expect(page.getByText("Corrected — replaced by a new payment with its own receipt")).toBeVisible();
  // the signed link opens in a new tab; headless Chromium downloads the PDF there, so check the served response itself
  const [pdf] = await Promise.all([
    page.context().waitForEvent("response", (response) => response.url().includes("/api/v1/files/signed/")),
    card.getByRole("button", { name: /^Download refund receipt RF-/ }).click(),
  ]);
  expect([pdf.status(), pdf.headers()["content-type"]]).toEqual([200, "application/pdf"]);
  // the only console error is the browser's log of the deliberate over-credit refusal above
  expect(consoleErrors.filter((text) => !text.includes("status of 422"))).toEqual([]);
});
