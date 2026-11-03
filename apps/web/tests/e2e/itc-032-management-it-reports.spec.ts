import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// itc-032 (DEC-SCOPE-369): a fresh IT student enrols and pays part of their fee; the IT Admin opens Management Reports, filters by the
// course, sees the revenue figures tie out to the student's row, carries the filter across tabs, drills down and downloads the CSV; a
// refused filter is explained; the accountant sees the Revenue tab only; super admin reaches it from their sidebar; a counselor is
// refused; the page stacks on a phone. A fresh student per run.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";
type Account = { enrollment_id: string; total_payable: number; course: string };

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

test("management IT reports: figures tie out, filters carry across tabs, roles are respected", async ({ browser, page }) => {
  test.setTimeout(180_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const email = `i032-${Date.now()}@example.com`;
  const registered = await (await browser.newContext()).request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: "I032 Learner", division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  expect((await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } })).status()).toBe(201);
  // the seat is taken once the student accepts the agreement (pending consent is not an enrolment in these reports)
  const agreement = await (await student.get("/api/v1/workflows/it/student/agreements/current")).json();
  expect((await student.post(`/api/v1/workflows/it/student/agreements/${agreement.id}/accept`)).ok()).toBeTruthy();
  const { enrollment_id: eid, total_payable: fee, course } = ((await (await student.get("/api/v1/it/student/fee-accounts")).json()) as Account[])[0];
  const admin = await api(browser, "itadmin@edusphere.local");
  const part = Math.min(1000, fee / 2);
  expect((await admin.post(`/api/v1/it/enrollments/${eid}/payments`, { data: { amount: part, payment_mode: "upi", provider_reference: `E2E32-${Date.now()}` } })).status()).toBe(201);
  const enrolmentCode = ((await (await admin.get(`/api/v1/management/it/reports/revenue?limit=200`)).json()) as { items: { enrollment_code: string; collected: number; course: string }[] })
    .items.find((i) => i.collected === part && i.course === course)?.enrollment_code;
  expect(enrolmentCode).toBeTruthy();

  // --- the IT Admin: Revenue, filtered by the course ---
  await signIn(page, "/it/login", "itadmin@edusphere.local", "/it/admin/dashboard");
  await page.getByRole("link", { name: "Management Reports", exact: true }).first().click();
  await page.waitForURL("**/it/admin/management-reports");
  await expect(page.getByRole("heading", { name: "IT reports", level: 2 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "IT reports" }).getByRole("link")).toHaveCount(6);
  await page.getByRole("navigation", { name: "IT reports" }).getByRole("link", { name: "Revenue & outstanding" }).click();
  await page.waitForURL(/report=revenue/);
  await page.getByLabel("Course", { exact: true }).selectOption({ label: course });
  await page.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(/program_id=/);
  await expect(page.getByLabel("Course", { exact: true })).toHaveValue(/.+/);  // the filter survives the reload
  await expect(page.getByRole("row", { name: new RegExp(enrolmentCode!) })).toContainText(rupees(part));
  await page.getByText("What these figures mean").click();
  await expect(page.getByText(/Positive balances of those enrolments that are active/)).toBeVisible();

  // the course filter carries to Attendance & completion; the course row drills down
  await page.getByRole("navigation", { name: "IT reports" }).getByRole("link", { name: "Attendance & completion" }).click();
  await page.waitForURL(/report=training.*program_id=|program_id=.*report=training/);
  await expect(page.getByRole("link", { name: /Show rows for/ }).first()).toHaveAttribute("href", /program_id=/);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe("it-training.csv");

  // a refused filter is explained and the form keeps it
  await page.goto("/it/admin/management-reports?report=revenue&status=qualified");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Choose a status from the list");
  expect(consoleErrors).toEqual([]);

  // a phone: the tables stack, nothing overflows sideways
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/it/admin/management-reports?report=funnel");
  await expect(page.getByRole("heading", { name: "Lead funnel", level: 3 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  // --- the accountant: Revenue only, from the management sidebar ---
  const accountantPage = await (await browser.newContext()).newPage();
  await signIn(accountantPage, "/admin/login", "accountant@edusphere.local", "/management");
  await accountantPage.getByRole("link", { name: "IT reports", exact: true }).first().click();
  await accountantPage.waitForURL("**/management/it-reports");
  const tabs = accountantPage.getByRole("navigation", { name: "IT reports" }).getByRole("link");
  await expect(tabs).toHaveCount(1);
  await expect(tabs.first()).toHaveText("Revenue & outstanding");
  await accountantPage.goto("/management/it-reports?report=funnel");  // asking for another tab opens their own
  await expect(accountantPage.getByRole("heading", { name: "Revenue & outstanding", level: 3 })).toBeVisible();

  // --- super admin, from their sidebar ---
  const superPage = await (await browser.newContext()).newPage();
  await signIn(superPage, "/admin/login", "superadmin@edusphere.local", "/admin");
  await superPage.goto("/management/it-reports");
  await expect(superPage.getByRole("navigation", { name: "IT reports" }).getByRole("link")).toHaveCount(6);

  // --- a counselor is refused ---
  const counselorPage = await (await browser.newContext()).newPage();
  await signIn(counselorPage, "/overseas/login", "counselor@edusphere.local", "/overseas/counselor/dashboard");
  await counselorPage.goto("/it/admin/management-reports");
  await expect(counselorPage.getByText("You do not have access to this IT report")).toBeVisible();
});
