import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-012 (DEC-SCOPE-345): the IT student adds their emergency contact on Profile; their IT counselor opens the record from My Students,
// sees it and sets a per-student start date and mode for an enrolment; a trainer gets no route to the record. Uses the seeded IT student
// (who has an enrolment) and a throwaway counselor; values are unique per run (the shared stack DB is never assumed clean).

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("the student adds an emergency contact; the counselor sees it and overrides an enrolment's dates; a trainer is refused", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const contact = `Ravi ${stamp}`;
  const counselorName = `Itc Record ${stamp}`;

  // The seeded student's id (the admin Students list is capped at 500 rows in a shared DB).
  await signIn(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  const student = await (await page.request.get("/api/v1/auth/me")).json();
  await page.request.post("/api/v1/auth/logout");

  // The IT Admin makes a throwaway IT counselor the seeded student's counselor (itc-003).
  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const created = await page.request.post("/api/v1/admin/users", { data: { role: "counselor", division: "it", full_name: counselorName, email: `itc012-c-${stamp}@example.local` } });
  expect(created.status()).toBe(201);
  const counselor = await created.json();
  await activateWithToken(page.request, counselor.development_welcome_token);
  const assigned = await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id, reason: "itc-012 e2e" } });
  expect(assigned.status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");

  // + The student adds an emergency contact; it is there after a reload.
  await signIn(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  await page.goto("/it/student/profile");
  await expect(page.getByRole("heading", { name: "My details" })).toBeVisible();
  await page.getByLabel("Emergency contact name").fill(contact);
  await page.getByLabel("Relation").fill("Father");
  await page.getByLabel("Emergency contact phone").fill("call me");
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByRole("alert")).toContainText("Emergency contact phone");
  await page.getByLabel("Emergency contact phone").fill("+91 98765 43210");
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Details saved." })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Emergency contact name")).toHaveValue(contact);
  await expect(page.getByRole("table", { name: "Enrolments" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save dates" })).toHaveCount(0); // overrides are staff-only
  await page.request.post("/api/v1/auth/logout");

  // The counselor opens the record from My Students and overrides the first enrolment's start date and mode.
  await signIn(page, counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto("/it/counselor/students");
  await page.locator("tr", { hasText: "Arjun Rao" }).getByRole("link", { name: /Profile/ }).click();
  await page.waitForURL(`**/it/counselor/students/${student.id}/profile`);
  await expect(page.getByLabel("Emergency contact name")).toHaveValue(contact);
  const editor = page.getByRole("group", { name: /^Dates for / }).first();
  await editor.getByLabel("Start date").fill("2031-01-05");
  await editor.getByLabel("Delivery mode").selectOption("Offline");
  await editor.getByRole("button", { name: "Save dates" }).click();
  await expect(editor.getByText("Dates saved.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Enrolments" })).toContainText("Set for this student");
  await editor.getByRole("button", { name: "Use batch dates" }).click(); // leave the seeded enrolment as it was
  await expect(editor.getByText("Dates saved.")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // − A trainer has no route to the record (no emergency contact).
  await signIn(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  for (const url of [`/api/v1/admin/it/students/${student.id}/profile`, `/api/v1/counselor/it/students/${student.id}/profile`]) {
    const response = await page.request.get(url);
    expect(response.status()).toBe(403);
    expect(await response.text()).not.toContain(contact);
  }
});
