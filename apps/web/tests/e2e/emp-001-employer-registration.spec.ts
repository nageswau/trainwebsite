import { test, expect } from "@playwright/test";

// EMP-001 -- Employer registration. Requires the stack running via `docker compose up`.

test("a company registers as an Employer and lands signed in on their own dashboard (EMP-001-AC01)", async ({ page }) => {
  await page.goto("/it/corporate-hiring");
  await page.getByRole("link", { name: "Register your company" }).click();
  await page.waitForURL("**/it/employer-register");

  const stamp = Date.now();
  await page.fill("#emp-reg-company", `Playwright Testing Co ${stamp}`);
  await page.fill("#emp-reg-website", "https://playwright-testing.example.com");
  await page.fill("#emp-reg-name", "Jordan Hiring Manager");
  await page.fill("#emp-reg-email", `emp001-${stamp}@example.com`);
  await page.fill("#emp-reg-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Register your company')");

  await page.waitForURL("**/it/employer/dashboard");
  await expect(page.getByRole("heading", { name: `Welcome, Playwright Testing Co ${stamp}` })).toBeVisible();
  await expect(page.getByText("Your account is active")).toBeVisible();
});

test("duplicate email registration shows a real error, not a silent failure (EMP-001-AC02)", async ({ page }) => {
  const stamp = Date.now();
  const email = `emp001-dup-${stamp}@example.com`;

  await page.goto("/it/employer-register");
  await page.fill("#emp-reg-company", `First Co ${stamp}`);
  await page.fill("#emp-reg-name", "First Registrant");
  await page.fill("#emp-reg-email", email);
  await page.fill("#emp-reg-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Register your company')");
  await page.waitForURL("**/it/employer/dashboard");

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/employer-register");
  await page.fill("#emp-reg-company", `Second Co ${stamp}`);
  await page.fill("#emp-reg-name", "Second Registrant");
  await page.fill("#emp-reg-email", email);
  await page.fill("#emp-reg-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Register your company')");

  await expect(page.locator(".form-error")).toContainText(/already exists/i);
});

test("the employer dashboard requires authentication (EMP-001-AC03)", async ({ page }) => {
  await page.goto("/it/employer/dashboard");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
});

test("a non-employer role cannot reach the employer profile API (EMP-001-AC03)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  const response = await page.request.get("/api/v1/employer/profile");
  expect(response.status()).toBe(403);
});
