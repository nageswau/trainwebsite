import { expect, test, type Page } from "@playwright/test";

import { activateWithToken } from "./helpers/welcome";

// itc-028 (DEC-SCOPE-351): an IT counselor writes notes on their student from My Students. Notes start internal; one shared (after a
// confirm) appears in the student's Updates, and the internal one never does. Throwaway accounts (the shared stack DB is never clean).

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

test("a counselor's internal note stays internal; a shared one reaches the student's Updates", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const password = `Itc028!${stamp}`;
  const [counselorEmail, studentEmail] = [`itc028-c-${stamp}@example.local`, `itc028-s-${stamp}@example.local`];
  await signIn(page, "itadmin@edusphere.local", PASSWORD, "/it/admin/dashboard");
  const counselor = await createUser(page, "counselor", `Itc Notes Counselor ${stamp}`, counselorEmail, password);
  const studentName = `Itc Notes Student ${stamp}`;
  const student = await createUser(page, "it_student", studentName, studentEmail, password);
  expect((await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id } })).status()).toBe(200);

  await signIn(page, counselorEmail, password, "/it/counselor/dashboard");
  await page.goto("/it/counselor/students");
  await page.locator("tr", { hasText: studentName }).getByRole("link", { name: /Notes for/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Notes: ${studentName}`);
  const [internal, shared] = [`Internal ${stamp}: weak on SQL joins`, `Shared ${stamp}: please add your GitHub link`];
  for (const body of [internal, shared]) {
    await page.getByLabel("New note").fill(body);
    await page.getByRole("button", { name: "Save note" }).click();
    await expect(page.getByText("Note saved. Only staff can see it.")).toBeVisible();
  }
  const sharedNote = page.locator("li", { hasText: shared });
  await expect(sharedNote.getByText("Internal")).toBeVisible(); // N4: internal by default
  page.once("dialog", (dialog) => dialog.accept());
  await sharedNote.getByRole("button", { name: "Share with student" }).click();
  await expect(sharedNote.getByText("Shared with student")).toBeVisible();

  await signIn(page, studentEmail, password, "/it/student/dashboard");
  await page.getByRole("link", { name: "Updates", exact: true }).click();
  await expect(page.getByText(shared)).toBeVisible();
  await expect(page.getByText(internal)).toHaveCount(0); // AC1
  expect(await page.content()).not.toContain(internal);
});
