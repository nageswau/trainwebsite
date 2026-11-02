import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-003 (DEC-SCOPE-337): the IT Admin assigns an IT student's counselor on the Students page, then moves them to another counselor
// with a reason; only the new counselor sees the student under Students, and the student's dashboard names their counselor.
// Throwaway accounts (the shared stack DB is never assumed to be clean).

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function createUser(page: Page, role: string, name: string, email: string) {
  const created = await page.request.post("/api/v1/admin/users", { data: { role, division: "it", full_name: name, email } });
  expect(created.status()).toBe(201);
  const user = await created.json();
  await activateWithToken(page.request, user.development_welcome_token);
  return user;
}

async function pick(page: Page, row: ReturnType<Page["locator"]>, button: string, counselor: string, reason?: string) {
  await row.getByRole("button", { name: button }).click();
  const field = page.getByRole("combobox", { name: "EduSphere counsellor" });
  await field.fill(counselor.split(" ").pop() as string);
  await page.getByRole("option", { name: new RegExp(counselor) }).click();
  if (reason) await page.getByRole("textbox", { name: "Reason for the change" }).fill(reason);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator(".form-message")).toHaveText(`${counselor} assigned.`);
}

test("the IT Admin assigns and moves an IT student's counselor; the counselor and the student see it", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const [c1Name, c2Name, studentName] = [`Itc Alpha ${stamp}`, `Itc Bravo ${stamp}`, `Itc Student ${stamp}`];
  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const c1 = await createUser(page, "counselor", c1Name, `itc003-c1-${stamp}@example.local`);
  const c2 = await createUser(page, "counselor", c2Name, `itc003-c2-${stamp}@example.local`);
  const student = await createUser(page, "it_student", studentName, `itc003-s-${stamp}@example.local`);

  await page.goto("/it/admin/students");
  const row = page.locator("tr", { hasText: studentName });
  await expect(row).toContainText("Not assigned");
  await pick(page, row, "Assign counsellor", c1Name);
  await expect(row).toContainText(c1Name);
  // AC2: a reassignment needs a reason (Save stays disabled without one).
  await row.getByRole("button", { name: "Change counsellor" }).click();
  await page.getByRole("combobox", { name: "EduSphere counsellor" }).fill("Bravo");
  await page.getByRole("option", { name: new RegExp(c2Name) }).click();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await page.getByRole("button", { name: "Cancel" }).click();
  await pick(page, row, "Change counsellor", c2Name, "Workload balance");
  await expect(row).toContainText(c2Name);
  await page.request.post("/api/v1/auth/logout");

  // AC3: C2 sees S; C1 no longer does (list and the per-student read).
  await signIn(page, c2.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.getByRole("navigation").getByRole("link", { name: "Students" }).click();
  await expect(page.getByRole("heading", { name: "My Students" })).toBeVisible();
  await expect(page.locator("tr", { hasText: studentName })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, c1.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto("/it/counselor/students");
  await expect(page.getByRole("heading", { name: "My Students" })).toBeVisible();
  await expect(page.locator("tr", { hasText: studentName })).toHaveCount(0);
  expect((await page.request.get(`/api/v1/counselor/it/students/${student.id}`)).status()).toBe(404);
  await page.request.post("/api/v1/auth/logout");

  // The student reads their own counselor on the dashboard.
  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await expect(page.getByText("Your counselor")).toBeVisible();
  await expect(page.getByText(c2Name)).toBeVisible();
});
