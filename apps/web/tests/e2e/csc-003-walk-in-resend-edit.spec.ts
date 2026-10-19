import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// csc-003 (DEC-SCOPE-228) -- on a pending walk-in row the counselor resends the link (then hits the 60 s cooldown) and fixes a
// mistyped email; the student activates under the corrected address and the row becomes Active with no actions. Requires the stack
// running with `python -m app.seed` applied. Counselor responses never carry the link token (S3), so the spec activates the account the
// way an admin would Re-send it (that response carries it in dev/test), as csc-002 and agn-002 do.

async function adminActivateStudent(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=overseas_student&provisioning_status=pending_setup")).json();
  const student = users.find((u: { email: string }) => u.email === email);
  // The ENH-003 cooldown is per account and shared by every sender: right after the counselor's own links the admin Re-send is 429 too.
  let response = await request.post(`/api/v1/admin/users/${student.id}/welcome-links`);
  if (response.status() === 429) {
    await new Promise((resolve) => setTimeout(resolve, (Number(response.headers()["retry-after"]) + 1) * 1000));
    response = await request.post(`/api/v1/admin/users/${student.id}/welcome-links`);
  }
  expect(response.status()).toBe(201);
  await activateWithToken(request, (await response.json()).development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

async function addWalkIn(page: Page, name: string, email: string) {
  const form = page.getByRole("form", { name: "Add a walk-in student" });
  await form.getByLabel("Full name").fill(name);
  await form.getByLabel("Email").fill(email);
  await form.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(`Account created for ${name}.`)).toBeVisible();
}

test("a counselor resends the link and fixes a mistyped email; the student activates under the new address (csc-003)", async ({ page, browser }) => {
  test.setTimeout(150_000); // includes the 60 s per-account cooldown before the admin Re-send
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && !message.text().includes("status of 429") && consoleErrors.push(message.text()));
  const unique = Date.now();
  const name = `Typo E2E ${unique}`;
  const fixed = `csc003-${unique}@example.local`;

  await signInAsFreshCounselor(page, "csc003");
  await page.goto("/overseas/counselor/students");
  await addWalkIn(page, name, `csc003-${unique}@exmaple.local`);

  const resend = page.getByRole("button", { name: `Resend link to ${name}` });
  await resend.click();
  await expect(page.getByText(`A new set-password link was emailed to csc003-${unique}@exmaple.local.`)).toBeVisible();
  await resend.click();
  await expect(page.getByText(/A link was just sent; wait \d+ seconds before re-sending/)).toBeVisible();

  await page.getByRole("button", { name: `Edit ${name}` }).click();
  const form = page.getByRole("form", { name: `Edit ${name}` });
  await form.getByLabel("Email").fill(fixed);
  const [patch] = await Promise.all([page.waitForResponse((r) => r.request().method() === "PATCH"), form.getByRole("button", { name: "Save" }).click()]);
  expect(patch.status()).toBe(200);
  expect(await patch.json()).not.toHaveProperty("development_welcome_token");
  await expect(page.getByText(`${name} updated. A new set-password link was emailed to ${fixed}.`)).toBeVisible();
  await expect(page.getByRole("button", { name: `Edit ${name}` })).toBeFocused();

  const studentContext = await browser.newContext();
  const student = await studentContext.newPage();
  await adminActivateStudent(student.request, fixed);
  await signIn(student, fixed, E2E_PASSWORD, "/overseas/student/dashboard");
  await studentContext.close();

  await page.reload();
  const row = page.getByRole("listitem").filter({ hasText: name });
  await expect(row.getByText("Active")).toBeVisible();
  await expect(row.getByRole("button")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("an edit to an address that is taken keeps the entry and says why, on a phone screen (csc-003)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const name = `Taken E2E ${Date.now()}`;
  await signInAsFreshCounselor(page, "csc003");
  await page.goto("/overseas/counselor/students");
  await addWalkIn(page, name, `taken-${Date.now()}@example.local`);
  await page.getByRole("button", { name: `Edit ${name}` }).click();
  const form = page.getByRole("form", { name: `Edit ${name}` });
  await form.getByLabel("Email").fill("student.overseas@edusphere.local");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: name }).getByText("Email already exists")).toBeVisible();
  await expect(form.getByLabel("Email")).toHaveValue("student.overseas@edusphere.local");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
