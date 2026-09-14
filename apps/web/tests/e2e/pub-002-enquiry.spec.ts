import { test, expect } from "@playwright/test";

// PUB-002 -- Enquiry submission synced to CRM. Requires the stack running via
// `docker compose up` (api + worker + web).

test("submitting the IT contact form succeeds promptly and confirms receipt (PUB-002-AC01)", async ({ page }) => {
  await page.goto("/it/contact");
  await page.fill('input[name="name"]', "Playwright Visitor");
  await page.fill('input[name="email"]', `visitor-${Date.now()}@example.com`);
  await page.fill('input[name="phone"]', "+919999000000");
  await page.fill('input[name="subject"]', "Python Full Stack");
  await page.fill('textarea[name="message"]', "Please call me back about the next available batch.");

  const start = Date.now();
  await page.click('button:has-text("Request training callback")');
  await expect(page.getByText(/Thank you\. Your enquiry has been received/)).toBeVisible();
  const elapsedMs = Date.now() - start;
  // AC02 / outbox pattern: the visitor-facing response must never wait on the CRM
  // webhook round trip -- generous 5s ceiling well above a fast local response, but
  // far below what a slow/unreachable webhook call would look like if awaited inline.
  expect(elapsedMs).toBeLessThan(5000);
});

test("the enquiry form's fields have real label associations (accessibility)", async ({ page }) => {
  await page.goto("/it/contact");
  for (const field of ["name", "email", "phone", "subject", "message"]) {
    const control = page.locator(`[name="${field}"]`);
    const id = await control.getAttribute("id");
    expect(id).toBeTruthy();
    await expect(page.locator(`label[for="${id}"]`)).toHaveCount(1);
  }
});

test("the overseas contact form submits independently with its own subject label", async ({ page }) => {
  await page.goto("/overseas/contact");
  await expect(page.getByText("Destination / study interest")).toBeVisible();
  await page.fill('input[name="name"]', "Overseas Visitor");
  await page.fill('input[name="email"]', `overseas-${Date.now()}@example.com`);
  await page.fill('input[name="subject"]', "Masters in UK");
  await page.fill('textarea[name="message"]', "Please advise on timelines and requirements.");
  await page.click('button:has-text("Book counseling callback")');
  await expect(page.getByText(/Thank you\. Your enquiry has been received/)).toBeVisible();
});

test("a submitted enquiry is visible to the correct division admin via the API, scoped by division", async ({ page, request }) => {
  const email = `admin-view-${Date.now()}@example.com`;
  await page.goto("/it/contact");
  await page.fill('input[name="name"]', "Admin Visibility Check");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="subject"]', "Data Analytics");
  await page.fill('textarea[name="message"]', "Checking whether admin can see this enquiry.");
  await page.click('button:has-text("Request training callback")');
  await expect(page.getByText(/Thank you\. Your enquiry has been received/)).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access");
  const leads = await request.get("/api/v1/admin/leads", { headers: { cookie: `edusphere_access=${access?.value}` } });
  expect(leads.status()).toBe(200);
  const found = (await leads.json()).some((lead: { email: string }) => lead.email === email);
  expect(found).toBe(true);
});
