import { test, expect, type Browser, type Page } from "@playwright/test";

// itc-002 (DEC-SCOPE-336) -- typed notifications with a record link. Requires the stack via `docker compose up` and `python -m app.seed`.
// An IT admin records a paid fee for the demo IT student; the student sees "Payment received" (no amount) in their new Notifications
// section, can filter it by type and opens the record it links to.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function recordPaidFee(browser: Browser, studentId: string) {
  const admin = await browser.newContext();
  const page = await admin.newPage();
  await signIn(page, "itadmin@edusphere.local", "/it/admin/dashboard");
  const response = await page.request.post("/api/v1/admin/payments", { data: { user_id: studentId, amount: 7321, status: "paid", reference_type: "service_fee" } });
  expect(response.status()).toBe(201);
  const { id } = await response.json();
  await admin.close();
  return id as string;
}

test("an IT student is told a payment was received and opens their fees from it", async ({ page, browser }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await signIn(page, "student.it@edusphere.local", "/it/student/dashboard");
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const paymentId = await recordPaidFee(browser, me.id);

  await page.getByRole("link", { name: "Notifications" }).first().click();
  await expect(page).toHaveURL(/\/it\/student\/notifications$/);
  await expect(page.getByRole("heading", { name: "Notifications" }).first()).toBeVisible();
  await expect(page.getByText("Send notification")).toHaveCount(0); // the admin workflow form is not on this page

  const list = page.getByRole("list", { name: "Notifications" });
  const notice = list.getByRole("listitem").filter({ hasText: "Payment received" }).first();
  await expect(notice).toBeVisible();
  await expect(notice).not.toContainText("7321");
  await expect(notice).not.toContainText("7,321");

  const typed = (await (await page.request.get("/api/v1/workflows/notifications")).json()).find((n: { entity_id: string }) => n.entity_id === paymentId);
  expect(typed).toMatchObject({ event_type: "it.fee.payment_received", entity_type: "payment", action_url: "/it/student/fees" });

  const type = page.getByLabel("Type");
  await type.selectOption({ label: "Payment received" });
  await expect(page.getByRole("status")).toContainText("Showing");
  for (const item of await list.getByRole("listitem").all()) await expect(item).toContainText("Payment received");
  await type.selectOption({ label: "All" });

  await notice.getByRole("link", { name: "Open: Payment received" }).click();
  await expect(page).toHaveURL(/\/it\/student\/fees$/);
  await expect(page.getByRole("heading", { name: "Fee Status" }).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("the section requires a signed-in IT student", async ({ page }) => {
  await page.goto("/it/student/notifications");
  await expect(page).toHaveURL(/\/it\/login/);
  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/student/notifications");
  await expect(page.getByRole("list", { name: "Notifications" })).toHaveCount(0);
});

for (const [name, width, height] of [["mobile", 375, 812], ["tablet", 768, 1024], ["desktop", 1280, 800]] as const) {
  test(`the Notifications section fits a ${name} screen`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await signIn(page, "student.it@edusphere.local", "/it/student/dashboard");
    await page.goto("/it/student/notifications");
    await expect(page.getByRole("heading", { name: "Notifications" }).first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `test-results/itc-002-${name}.png`, fullPage: true });
  });
}
