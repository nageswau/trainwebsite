import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// nehn-021 (DEC-SCOPE-309): discount authority follows the `discounts.add` grant. The accountant holds no grant by default; a super
// admin grants payments.view + discounts.add and the accountant discounts from /management/payments. Grants are role-wide, so every
// test restores the accountant's seed (none) in `finally`.

const SUPER = { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" };
const ACCOUNTANT = "accountant@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function asSuper<T>(request: APIRequestContext, work: () => Promise<T>): Promise<T> {
  await request.post("/api/v1/auth/login", { data: SUPER });
  try {
    return await work();
  } finally {
    await request.post("/api/v1/auth/logout");
  }
}

async function setAccountantGrants(request: APIRequestContext, permissions: string[]) {
  await asSuper(request, async () => {
    const response = await request.put("/api/v1/admin/roles/accountant/permissions", { data: { permissions } });
    expect(response.status(), await response.text()).toBe(200);
  });
}

/** A fresh pending IT fee for the seeded IT student, so the test never depends on what else is in the shared DB. */
async function pendingFee(request: APIRequestContext): Promise<string> {
  return asSuper(request, async () => {
    const users = await (await request.get("/api/v1/admin/users?role=it_student")).json();
    const student = users.find((u: { email: string }) => u.email === "student.it@edusphere.local");
    const response = await request.post("/api/v1/admin/payments", { data: { user_id: student.id, reference_type: "service_fee", amount: 10000, currency: "INR", provider: "manual", status: "pending" } });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()).id;
  });
}

async function signInAccountant(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", ACCOUNTANT);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => url.pathname.startsWith("/management"));
}

test.describe.configure({ mode: "serial" });

test("AC1: without the grants the accountant sees no Payments link, a grant hint and no discount form", async ({ page }) => {
  await setAccountantGrants(page.request, []);
  await signInAccountant(page);
  await expect(page.locator(".portal-nav").getByRole("link", { name: "Management activity" })).toBeVisible();
  await expect(page.locator(".portal-nav").getByRole("link", { name: "Payments", exact: true })).toHaveCount(0);
  await page.goto("/management/payments");
  await expect(page.getByText(/permission to view payments/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Apply discount" })).toHaveCount(0);
});

test("AC2/AC3: once granted, the accountant opens Payments and discounts a fee with a reason", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    const paymentId = await pendingFee(admin.request);
    await setAccountantGrants(admin.request, ["payments.view", "discounts.add"]);
    await signInAccountant(page);
    await page.locator(".portal-nav").getByRole("link", { name: "Payments", exact: true }).click();
    await page.waitForURL("**/management/payments");
    await expect(page.getByRole("heading", { name: "Payments", level: 2 })).toBeVisible();
    await expect(page.getByText(paymentId).first()).toBeVisible();

    const form = page.locator(".action-card").filter({ has: page.getByRole("heading", { name: "Apply discount" }) });
    await form.getByLabel("Payment reference").fill(paymentId);
    await form.getByLabel("New (discounted) amount").fill("9000");
    await form.getByLabel("Reason").fill("10% scholarship");
    await form.getByRole("button", { name: "Apply discount" }).click();
    await expect(page.getByText("Discount applied.")).toBeVisible();

    const rows = await (await page.request.get("/api/v1/admin/payments")).json();
    expect(rows.find((row: { id: string }) => row.id === paymentId).amount).toBe(9000);
  } finally {
    await setAccountantGrants(admin.request, []);
    await admin.close();
  }
});

test("the accountant's Payments page fits a phone", async ({ page, browser }) => {
  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    await setAccountantGrants(admin.request, ["payments.view", "discounts.add"]);
    await page.setViewportSize({ width: 390, height: 844 });
    await signInAccountant(page);
    await page.goto("/management/payments");
    await expect(page.getByRole("heading", { name: "Apply discount" })).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
  } finally {
    await setAccountantGrants(admin.request, []);
    await admin.close();
  }
});
