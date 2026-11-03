import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-017 (DEC-SCOPE-368): a fresh IT student pays part of their fee; the IT Admin finds today's collection and the student's balance in
// Accounts (filtered by the course) and downloads the CSV; the accountant reads the same figures from the management sidebar; a counselor
// is refused. A fresh student per run.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
type Account = { enrollment_id: string; balance: number; total_payable: number; course: string };

async function api(browser: Browser, email: string, password = DEMO, division = "it"): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password, division } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", DEMO);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const rupees = (value: number) => `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

test("the IT Admin and the accountant read collections and balances; a counselor is refused", async ({ browser, page }) => {
  test.setTimeout(150_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const email = `i017-${Date.now()}@example.com`;
  const registered = await (await browser.newContext()).request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: "I017 Learner", division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  const { enrollment_id: eid, total_payable: fee, course } = ((await (await student.get("/api/v1/it/student/fee-accounts")).json()) as Account[])[0];
  const admin = await api(browser, "itadmin@edusphere.local");
  const part = Math.min(1000, fee / 2);
  expect((await admin.post(`/api/v1/it/enrollments/${eid}/payments`, { data: { amount: part, payment_mode: "upi", provider_reference: `E2E-${Date.now()}` } })).status()).toBe(201);

  // --- the IT Admin ---
  await signIn(page, "/it/login", "itadmin@edusphere.local", "/it/admin/dashboard");
  await page.getByRole("link", { name: "Accounts", exact: true }).first().click();
  await page.waitForURL("**/it/admin/accounts");
  await expect(page.getByRole("heading", { name: "Accounts", level: 2 })).toBeVisible();
  await page.getByLabel("Course").selectOption({ label: course });
  await page.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(/program_id=/);
  await expect(page.getByLabel("Course")).toHaveValue(/.+/); // the filter survives the reload
  await expect(page.getByRole("table", { name: "Collections" })).toBeVisible();

  await page.getByRole("link", { name: "Outstanding" }).click();
  await page.waitForURL(/report=outstanding/);
  const row = page.getByRole("row", { name: /I017 Learner/ });
  await expect(row).toContainText(rupees(fee - part));
  await expect(page.getByRole("link", { name: "I017 Learner" })).toHaveAttribute("href", /\/it\/admin\/students\/.+\/profile/);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe("it-outstanding.csv");
  await expect(page.getByText("Report downloaded.")).toBeVisible();

  // a refused filter is explained and the form keeps it
  await page.goto("/it/admin/accounts?report=collections&date_from=2024-01-01&date_to=2026-01-01");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Choose a date range of at most 366 days");
  await expect(page.getByLabel("From")).toHaveValue("2024-01-01");
  expect(consoleErrors).toEqual([]);

  // --- the accountant (Q-17), from the management sidebar ---
  const accountantPage = await (await browser.newContext()).newPage();
  await signIn(accountantPage, "/admin/login", "accountant@edusphere.local", "/management");
  await accountantPage.getByRole("link", { name: "IT fee accounts" }).click();
  await accountantPage.waitForURL("**/management/it-accounts");
  await accountantPage.getByRole("link", { name: "Outstanding" }).click();
  await expect(accountantPage.getByRole("row", { name: /I017 Learner/ })).toContainText(rupees(fee - part));
  await expect(accountantPage.getByRole("link", { name: "I017 Learner" })).toHaveCount(0); // no student record page for the accountant

  // --- a counselor is refused ---
  const counselorPage = await (await browser.newContext()).newPage();
  await signIn(counselorPage, "/overseas/login", "counselor@edusphere.local", "/overseas/counselor/dashboard");
  await counselorPage.goto("/it/admin/accounts");
  await expect(counselorPage.getByText("You do not have access to IT accounts")).toBeVisible();
});
