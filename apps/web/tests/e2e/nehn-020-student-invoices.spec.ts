import { test, expect } from "@playwright/test";

// nehn-020 (DEC-SCOPE-290): the student's payment document is the receipt. The fee card offers no invoice, the invoice route answers
// 404 to the student, and the IT Admin can still download the (still generated) invoice. Own throwaway student (RAID.md I-06); no
// Razorpay call -- the paid fee is a manual payment.

test("a student downloads the receipt and gets no invoice; the admin keeps the invoice", async ({ page, request }) => {
  const unique = Date.now();
  const email = `nehn020-${unique}@example.com`;
  const registered = await request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: `NEHN-020 Student ${unique}`, division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  const userId = (await registered.json()).user.id;

  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
  const created = await page.request.post("/api/v1/admin/payments", { data: { user_id: userId, reference_type: "service_fee", amount: 500, currency: "INR", provider: "manual", status: "paid" } });
  expect(created.ok()).toBeTruthy();
  const paymentId = (await created.json()).id;
  const adminInvoice = await page.request.get(`/api/v1/payments/${paymentId}/invoice`);
  expect(adminInvoice.status()).toBe(200);
  expect((await adminInvoice.json()).url).toBeTruthy();
  await page.context().clearCookies();

  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
  await page.goto("/it/student/fees");

  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Fee Payments" }) });
  await expect(card.getByRole("button", { name: "Receipt" })).toBeVisible();
  await expect(card.getByRole("button", { name: /invoice/i })).toHaveCount(0);

  const [receiptRequest] = await Promise.all([
    page.context().waitForEvent("request", (req) => req.url().includes("/api/v1/files/signed/")),
    card.getByRole("button", { name: "Receipt" }).click(),
  ]);
  expect((await receiptRequest.response())?.status()).toBe(200);

  const studentInvoice = await page.request.get(`/api/v1/payments/${paymentId}/invoice`);
  expect(studentInvoice.status()).toBe(404);
  expect((await studentInvoice.json()).detail).toBe("Invoices are not issued to students. Download your receipt instead.");
});
