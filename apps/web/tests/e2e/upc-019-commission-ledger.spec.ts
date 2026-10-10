import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-019 (AC1, AC2, AC3, P1): a signed commission agreement pays 15% of a GBP 18,000 programme on enrolment. Once a student's
// application is enrolled, the head sees GBP 2,700.00 expected on the university page, records a lump-sum receipt for the January intake
// (validation first), sees Outstanding fall, removes it again, and sees F10 / F11 on University Performance. The manager reads the ledger
// but cannot record; an overseas_admin sees no commission anywhere. The page fits a phone. Throwaway accounts via the real admin API.

const day = (offset: number) => new Date(Date.now() + 330 * 60_000 + offset * 86_400_000).toISOString().slice(0, 10); // IST

async function apiLogin(request: APIRequestContext, email: string, password: string, division: string) {
  await request.post("/api/v1/auth/logout");
  const response = await request.post("/api/v1/auth/login", { data: { email, password, division } });
  expect(response.ok(), await response.text()).toBe(true);
}

async function call(request: APIRequestContext, method: "post" | "patch", url: string, data: unknown) {
  const response = await request[method](url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  const r = page.request;
  await apiLogin(r, "superadmin@edusphere.local", "Demo@123", "global");
  const head = await call(r, "post", "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc019-h-${stamp}@example.local` });
  const manager = await call(r, "post", "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc019-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U19-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await call(r, "post", "/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc019-a-${stamp}@example.local` });
  const countries = await (await r.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await call(r, "post", "/api/v1/partnership/universities", { name: `E2E Ledger University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await call(r, "post", `/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await r.post("/api/v1/auth/logout");
  for (const user of [head, manager, admin]) await activateWithToken(r, user.development_welcome_token);

  // The manager adds the programme and drafts the agreement with its term, then sends it for review.
  await apiLogin(r, manager.email, E2E_PASSWORD, "overseas");
  const uni = `/api/v1/partnership/universities/${university.id}`;
  const { course } = await call(r, "post", `${uni}/courses`, { title: "MSc Data Science", level: "PG", category: "Technology", duration: "1 year", tuition_amount: "18000", tuition_currency: "GBP" });
  let { agreement } = await call(r, "post", `${uni}/agreements`, { agreement_type: "commission_agreement", start_date: day(-10), expiry_date: day(3 * 365), exclusivity: "non_exclusive" });
  await call(r, "post", `/api/v1/partnership/agreements/${agreement.id}/commission-terms`, { commission_percent: "15", currency: "GBP", trigger: "enrolment" });
  const move = async (to: string) => ({ agreement } = await call(r, "post", `/api/v1/partnership/agreements/${agreement.id}/status`, { from_status: agreement.status, to_status: to }));
  for (const to of ["sent", "under_review"]) await move(to);
  await apiLogin(r, head.email, E2E_PASSWORD, "global");
  await move("approved");
  await apiLogin(r, manager.email, E2E_PASSWORD, "overseas");
  const uploaded = await r.post(`${uni}/documents`, {
    multipart: { kind: "commission_agreement", title: `Signed agreement ${stamp}`, file: { name: "signed.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF\n") } },
  });
  expect(uploaded.ok(), await uploaded.text()).toBe(true);
  ({ agreement } = await call(r, "patch", `/api/v1/partnership/agreements/${agreement.id}`, {
    document_id: (await uploaded.json()).document.id, edusphere_signatory_user_id: manager.id, edusphere_signed_on: day(-1),
    university_signatory_name: "Prof. Registrar", university_signed_on: day(-2),
  }));
  await move("signed");

  // A student applies for the programme; the overseas admin marks the application enrolled.
  await apiLogin(r, "student.overseas@edusphere.local", "Demo@123", "overseas");
  const application = await call(r, "post", "/api/v1/workflows/overseas/applications", { university_id: university.id, course_id: course.id, intake: "Jan 2027" });
  await apiLogin(r, "overseasadmin@edusphere.local", "Demo@123", "overseas");
  await call(r, "patch", `/api/v1/workflows/overseas/applications/${application.id}`, { status: "enrolled" });
  await r.post("/api/v1/auth/logout");
  return { head, manager, admin, university };
}

async function signIn(page: Page, loginPath: string, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("the head sees commission expected, records and removes a receipt; nobody else can", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const { head, manager, admin, university } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;
  const ledger = page.getByRole("region", { name: "Commission (restricted)" });
  const totals = ledger.getByRole("table", { name: "Commission by currency" });
  const gbp = totals.getByRole("row", { name: /GBP/ });

  // AC1: 15% of GBP 18,000 on enrolment.
  await signIn(page, "/admin/login", head.email);
  await page.goto(universityPage);
  await expect(gbp).toContainText("GBP 2,700.00");
  await expect(gbp.locator("td").nth(2)).toHaveText("GBP 2,700.00"); // Outstanding
  await expect(ledger.getByRole("table", { name: "Enrolled applications and their expected commission" })).toContainText("MSc Data Science");
  await expect(ledger.getByText("No receipts recorded yet.")).toBeVisible();

  // N1 + P1 + AC2: validation, then a lump sum for the January intake linked to the application.
  await ledger.getByRole("button", { name: "Record a receipt" }).click();
  const form = ledger.getByRole("form", { name: "Record a commission receipt" });
  await form.getByLabel("Amount").fill("-5");
  await form.getByRole("button", { name: "Save receipt" }).click();
  await expect(form.locator(".form-error[role=alert]")).toHaveText("The amount must be more than 0.");
  await form.getByLabel("Amount").fill("1000");
  await form.getByLabel("Currency").selectOption("GBP");
  await form.getByLabel("Reference").fill(`SWIFT-JAN-${stamp}`);
  await form.getByLabel("Note").fill("Lump sum for the January intake");
  await form.getByRole("checkbox").first().check();
  await form.getByRole("button", { name: "Save receipt" }).click();
  await expect(ledger.locator("p[role=status]")).toHaveText("Receipt recorded.");
  await expect(gbp.locator("td").nth(2)).toHaveText("GBP 1,700.00");
  const receipts = ledger.getByRole("table", { name: "Commission received" });
  await expect(receipts).toContainText(`SWIFT-JAN-${stamp}`);

  // The same reference again is refused with the API's message (409).
  await ledger.getByRole("button", { name: "Record a receipt" }).click();
  await form.getByLabel("Amount").fill("10");
  await form.getByLabel("Currency").selectOption("GBP");
  await form.getByLabel("Reference").fill(`swift-jan-${stamp}`);
  await form.getByRole("button", { name: "Save receipt" }).click();
  await expect(form.locator(".form-error[role=alert]")).toHaveText("This reference is already recorded for this university");
  await form.getByRole("button", { name: "Cancel" }).click();

  // F10 / F11 on University Performance this month.
  await page.goto("/partnership/performance");
  const row = page.getByRole("rowheader", { name: university.name }).locator("xpath=..");
  await expect(row).toContainText("GBP 2,700.00");
  await expect(row).toContainText("GBP 1,000.00");

  // The manager reads the ledger but cannot record or remove (Q-20).
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  await expect(gbp.locator("td").nth(2)).toHaveText("GBP 1,700.00");
  await expect(ledger.getByRole("button", { name: "Record a receipt" })).toHaveCount(0);
  await expect(ledger.getByRole("button", { name: /Remove receipt/ })).toHaveCount(0);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.reload();
  await expect(gbp).toBeVisible();
  expect(await noSideScroll(page)).toBeLessThanOrEqual(1);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC3: an overseas_admin sees no commission on the university page or the performance page, and the API refuses them.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(universityPage);
  await expect(page.getByRole("heading", { name: university.name })).toBeVisible();
  await expect(ledger).toHaveCount(0);
  expect((await page.request.get(`/api/v1/partnership/universities/${university.id}/commission`)).status()).toBe(403);
  await page.goto("/partnership/performance");
  await expect(page.getByRole("columnheader", { name: /Commission/ })).toHaveCount(0);

  // The head removes the receipt again; Outstanding is back to the full amount.
  await signIn(page, "/admin/login", head.email);
  await page.goto(universityPage);
  await ledger.getByRole("button", { name: `Remove receipt SWIFT-JAN-${stamp}` }).click();
  await ledger.getByRole("group", { name: `Remove receipt SWIFT-JAN-${stamp}?` }).getByRole("button", { name: "Yes, remove" }).click();
  await expect(ledger.locator("p[role=status]")).toHaveText("Receipt removed.");
  await expect(gbp.locator("td").nth(2)).toHaveText("GBP 2,700.00");
});
