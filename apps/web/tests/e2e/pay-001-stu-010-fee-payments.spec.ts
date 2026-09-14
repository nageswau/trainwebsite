import { test, expect } from "@playwright/test";

// PAY-001/STU-010 -- Fee payment, EMI, invoices, receipts. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied, and real Razorpay
// TEST-mode credentials in `.env` (checkout hits the live Razorpay TEST API).
//
// Registers its own throwaway student rather than mutating the seeded
// `student.it@edusphere.local` account's payments -- same "own throwaway record"
// convention as ADM-010's own spec (RAID.md I-06).

async function loginAsItAdmin(page: import("@playwright/test").Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
}

test("@external student pays a pending fee via a real Razorpay checkout session and downloads the invoice/receipt once paid (STU-010-AC01/PAY-001-AC01)", async ({ page, request }) => {
  const unique = Date.now();
  const email = `pay001-${unique}@example.com`;
  const registered = await request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: `PAY-001 Student ${unique}`, division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  const userId = (await registered.json()).user.id;

  await loginAsItAdmin(page);
  const pending = await page.request.post("/api/v1/admin/payments", { data: { user_id: userId, reference_type: "course_fee", amount: 1500, currency: "INR", provider: "razorpay" } });
  expect(pending.ok()).toBeTruthy();
  const paid = await page.request.post("/api/v1/admin/payments", { data: { user_id: userId, reference_type: "service_fee", amount: 500, currency: "INR", provider: "manual", status: "paid" } });
  expect(paid.ok()).toBeTruthy();

  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/fees");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Fee Payments" }) });
  await expect(card).toBeVisible();

  // Pay the still-pending fee -- a real order-creation call against Razorpay's TEST API,
  // followed by Razorpay's own real checkout widget actually opening (previously the
  // backend's real order/key were discarded and only a static message shown -- RAID.md
  // I-23).
  await card.getByRole("button", { name: "Pay Now" }).first().click();
  // The real Razorpay checkout renders inside its own iframe -- a plain page-level text
  // locator can't see into it, so this checks for the iframe itself (a genuine
  // checkout.razorpay.com/api.razorpay.com frame), the strongest available signal that
  // the real widget actually opened rather than the old static message. Not driving
  // Razorpay's own hosted UI further than that (entering a test card, closing via their
  // own controls) -- that's testing their frontend, not ours. Reloading the page is a
  // reliable way to tear the real third-party modal back down before continuing.
  await expect(page.locator("iframe[src*='razorpay.com']").first()).toBeVisible();
  await page.reload();
  await expect(card).toBeVisible();

  // The already-paid fee shows both documents; download the invoice via its real signed URL.
  const [invoiceRequest] = await Promise.all([
    page.context().waitForEvent("request", (req) => req.url().includes("/local-files/invoices/")),
    card.getByRole("button", { name: "Invoice" }).last().click(),
  ]);
  expect((await invoiceRequest.response())?.status()).toBe(200);

  const [receiptRequest] = await Promise.all([
    page.context().waitForEvent("request", (req) => req.url().includes("/local-files/receipts/")),
    card.getByRole("button", { name: "Receipt" }).click(),
  ]);
  expect((await receiptRequest.response())?.status()).toBe(200);
});

test("an admin creates an EMI schedule and the student sees the installment timeline (STU-010-AC01)", async ({ page, request }) => {
  const unique = Date.now();
  const email = `pay001-emi-${unique}@example.com`;
  const registered = await request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: `PAY-001 EMI Student ${unique}`, division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  const userId = (await registered.json()).user.id;

  await loginAsItAdmin(page);
  const schedule = await page.request.post("/api/v1/admin/payments/emi-schedule", {
    data: {
      user_id: userId,
      reference_type: "course_fee",
      currency: "INR",
      installments: [
        { amount: 1000, due_date: "2026-10-15" },
        { amount: 1000, due_date: "2026-11-15" },
      ],
    },
  });
  expect(schedule.ok()).toBeTruthy();

  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/fees");
  await expect(page.getByText("EMI Schedule")).toBeVisible();
  await expect(page.getByText("Installment 1:")).toBeVisible();
  await expect(page.getByText("Installment 2:")).toBeVisible();
});

test("fee payment checkout requires authentication", async ({ request }) => {
  const response = await request.post("/api/v1/payments/00000000-0000-0000-0000-000000000000/checkout", { data: { provider: "razorpay" } });
  expect(response.status()).toBe(401);
});
