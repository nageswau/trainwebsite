import { expect, test, type Page } from "@playwright/test";

import { activateWithToken } from "./helpers/welcome";

// itc-029 (DEC-SCOPE-358): the IT student 360. A counselor opens their student from My Students and sees every section, a note added
// on the Notes page shows on the 360 straight away (AC1); HR opens the same student's 360 from its student page without the fee section
// (Q-28); another counselor gets a not-found page (AC2). Throwaway accounts (the shared stack DB is never clean).

const PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function createUser(page: Page, role: string, name: string, email: string, password: string) {
  const created = await page.request.post("/api/v1/admin/users", { data: { role, division: "it", full_name: name, email } });
  expect(created.status()).toBe(201);
  const user = await created.json();
  await activateWithToken(page.request, user.development_welcome_token, password);
  return user;
}

const section = (page: Page, name: string) => page.getByRole("heading", { level: 3, name });

test("the counselor, HR and another counselor each get their own student 360", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const password = `Itc029!${stamp}`;
  const emails = { counselor: `itc029-c-${stamp}@example.local`, other: `itc029-o-${stamp}@example.local`, hr: `itc029-h-${stamp}@example.local`, student: `itc029-s-${stamp}@example.local` };
  await signIn(page, "itadmin@edusphere.local", PASSWORD, "/it/admin/dashboard");
  const counselor = await createUser(page, "counselor", `Itc360 Counselor ${stamp}`, emails.counselor, password);
  await createUser(page, "counselor", `Itc360 Other ${stamp}`, emails.other, password);
  await createUser(page, "hr_team", `Itc360 HR ${stamp}`, emails.hr, password);
  const studentName = `Itc360 Student ${stamp}`;
  const student = await createUser(page, "it_student", studentName, emails.student, password);
  expect((await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id } })).status()).toBe(200);

  // The counselor: My Students -> Open
  await signIn(page, emails.counselor, password, "/it/counselor/dashboard");
  await page.goto("/it/counselor/students");
  await page.locator("tr", { hasText: studentName }).getByRole("link", { name: `Open ${studentName}` }).click();
  await expect(page).toHaveURL(new RegExp(`/it/counselor/students/${student.id}$`));
  await expect(page.getByRole("heading", { level: 2, name: studentName })).toHaveText(studentName);
  for (const name of ["Contact", "Lead history", "Courses and progress", "Risk", "Fees", "Recent trainer feedback", "Resume and HR stage", "Notes", "Notifications sent"]) {
    await expect(section(page, name)).toBeVisible();
  }
  await expect(page.getByText("No enrolments yet.")).toBeVisible(); // E: a student with no enrolment yet

  // AC1: a note added on its own page is on the 360 at once
  const note = `Itc360 note ${stamp}`;
  await page.getByRole("link", { name: "Notes", exact: true }).first().click();
  await page.getByLabel("New note").fill(note);
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByText("Note saved. Only staff can see it.")).toBeVisible();
  await page.goto(`/it/counselor/students/${student.id}`);
  await expect(page.getByText(note)).toBeVisible();

  // HR: the student page -> 360 view, with no fee section (Q-28)
  await signIn(page, emails.hr, password, "/it/hr/dashboard");
  await page.goto(`/it/hr/students/${student.id}`);
  await page.getByRole("link", { name: "360 view" }).click();
  await expect(page.getByRole("heading", { level: 2, name: studentName })).toHaveText(studentName);
  await expect(section(page, "Notes")).toBeVisible();
  await expect(page.getByText(note)).toBeVisible();
  for (const name of ["Fees", "Lead history", "Risk", "Notifications sent"]) await expect(section(page, name)).toHaveCount(0);

  // AC2: another counselor's student is not found
  await signIn(page, emails.other, password, "/it/counselor/dashboard");
  const response = await page.goto(`/it/counselor/students/${student.id}`);
  expect(response?.status()).toBe(404);
  await expect(page.getByText(studentName)).toHaveCount(0);
});
