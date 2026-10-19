import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// csc-002 (DEC-SCOPE-227) -- an overseas counselor creates a walk-in student's login on the Students page; the student sets a password
// and signs in; the counselor sees them as Active and can book them. Requires the stack running with `python -m app.seed` applied. The
// create response never carries the link token (S3), so the spec activates the account the way an admin would Re-send it (the admin
// Re-send response carries it in dev/test), as agn-002 does.

async function adminActivateStudent(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=overseas_student&provisioning_status=pending_setup")).json();
  const student = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${student.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

async function addWalkIn(page: Page, name: string, email: string) {
  const form = page.getByRole("form", { name: "Add a walk-in student" });
  await form.getByLabel("Full name").fill(name);
  await form.getByLabel("Email").fill(email);
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/counselor/students"),
    form.getByRole("button", { name: "Create account" }).click(),
  ]);
  expect(response.status()).toBe(201);
  expect(await response.json()).not.toHaveProperty("development_welcome_token");
}

test("a counselor creates a walk-in student who sets a password, signs in and can be booked (csc-002)", async ({ page, browser }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const unique = Date.now();
  const name = `Walk-in E2E ${unique}`;
  const email = `csc002-${unique}@example.local`;

  await signInAsFreshCounselor(page, "csc002");
  await page.goto("/overseas/counselor/students");
  await addWalkIn(page, name, email);
  await expect(page.getByText(`Account created for ${name}.`)).toBeVisible();
  const row = page.getByRole("listitem").filter({ hasText: name });
  await expect(row.getByText("Set-up pending")).toBeVisible();

  const studentContext = await browser.newContext();
  const student = await studentContext.newPage();
  await adminActivateStudent(student.request, email);
  await signIn(student, email, E2E_PASSWORD, "/overseas/student/dashboard");
  await expect(student.getByText(name).first()).toBeVisible();
  await studentContext.close();

  await page.reload();
  await expect(page.getByRole("listitem").filter({ hasText: name }).getByText("Active")).toBeVisible();
  await page.goto("/overseas/counselor/appointments");
  await page.getByRole("combobox", { name: "Student reference" }).fill(String(unique));
  await expect(page.getByRole("option", { name: new RegExp(name) })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("the walk-in form refuses an existing email and fits a phone screen (csc-002)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signInAsFreshCounselor(page, "csc002");
  await page.goto("/overseas/counselor/students");
  const form = page.getByRole("form", { name: "Add a walk-in student" });
  await form.getByLabel("Full name").fill("Already Here");
  await form.getByLabel("Email").fill("student.overseas@edusphere.local");
  await form.getByRole("button", { name: "Create account" }).click();
  await expect(form.getByText("Email already exists")).toBeVisible();
  await expect(form.getByLabel("Email")).toHaveValue("student.overseas@edusphere.local");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
