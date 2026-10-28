import { test, expect } from "@playwright/test";

// nehn-019 (DEC-SCOPE-312) AC2/AC5: the IT Admin discounts a fee through the "Apply discount" form; the gross survives beside the net
// amount, and the student's fee card shows original, discount and payable, and a paid fee its paid date. Own throwaway student
// (RAID.md I-06); no Razorpay call -- the paid fee is a manual payment.

test("a discounted fee shows original, discount and payable; a paid fee its paid date", async ({ page, request }) => {
  const unique = Date.now();
  const email = `nehn019-${unique}@example.com`;
  const registered = await request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: `NEHN-019 Student ${unique}`, division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  const userId = (await registered.json()).user.id;

  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
  const pending = await page.request.post("/api/v1/admin/payments", { data: { user_id: userId, reference_type: "service_fee", amount: 10000, currency: "INR", provider: "manual" } });
  const paid = await page.request.post("/api/v1/admin/payments", { data: { user_id: userId, reference_type: "service_fee", amount: 500, currency: "INR", provider: "manual", status: "paid" } });
  expect(pending.ok() && paid.ok()).toBeTruthy();
  const pendingId = (await pending.json()).id;

  await page.goto("/it/admin/payments");
  const form = page.locator("form", { has: page.getByRole("button", { name: "Apply discount" }) });
  await form.getByLabel("Payment reference").fill(pendingId);
  await form.getByLabel("New (discounted) amount").fill("8000");
  await form.getByLabel("Reason").fill("Merit scholarship");
  await form.getByRole("button", { name: "Apply discount" }).click();
  await expect(form.getByText("Discount applied.")).toBeVisible();
  const row = (await (await page.request.get("/api/v1/admin/payments")).json()).find((r: { id: string }) => r.id === pendingId);
  expect([row.amount, row.gross_amount, row.discount_amount, row.discount_reason]).toEqual([8000, 10000, 2000, "Merit scholarship"]);
  await page.context().clearCookies();

  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/**");
  await page.goto("/it/student/fees");
  await expect(page.getByText("Original INR 10,000 · Discount INR 2,000")).toBeVisible();
  await expect(page.getByText(/^Payable INR 8,000/)).toBeVisible();
  await expect(page.getByText(/^Paid on \d{2} \w{3} \d{4}$/)).toBeVisible();
});
