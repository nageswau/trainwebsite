import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// itc-033 (DEC-SCOPE-357 C1-C3): an IT student (no phone on file) turns "Phone calls from our team" off on their profile; the choice
// survives a reload; their IT counselor and the IT Admin see "No phone calls" on the student record; turning it back on clears it.
// A throwaway student and counselor, so no other spec's counselor link on the seeded student moves while it runs.

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const callsBox = (page: Page) => page.getByRole("checkbox", { name: /^Phone calls from our team/ });
const saveSettings = (page: Page) => page.getByRole("button", { name: "Save notification settings" }).click();

test("a student opts out of phone calls and their counselor and the IT Admin see it", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();

  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const student = await createAndActivate(page.request, "/api/v1/admin/users", { role: "it_student", division: "it", full_name: `Itc Calls Student ${stamp}`, email: `itc033-s-${stamp}@example.local` });
  const counselor = await createAndActivate(page.request, "/api/v1/admin/users", { role: "counselor", division: "it", full_name: `Itc Calls ${stamp}`, email: `itc033-c-${stamp}@example.local` });
  expect((await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id, reason: "itc-033 e2e" } })).status()).toBe(200);
  await page.goto(`/it/admin/students/${student.id}/profile`);
  await expect(page.getByRole("heading", { name: `Student record: Itc Calls Student ${stamp}` })).toBeVisible();
  await expect(page.getByTestId("calls-opt-out")).toHaveCount(0); // allowed by default
  await page.request.post("/api/v1/auth/logout");

  // + the student turns calls off without any phone on file, and it survives a reload.
  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await page.goto("/account/profile");
  await expect(callsBox(page)).toBeChecked();
  await expect(callsBox(page)).toBeEnabled();
  await callsBox(page).uncheck();
  await saveSettings(page);
  await expect(page.getByText("Notification settings saved.")).toBeVisible();
  await page.reload();
  await expect(callsBox(page)).not.toBeChecked();
  await page.request.post("/api/v1/auth/logout");

  // the counselor and the IT Admin see it, read-only.
  await signIn(page, counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/students/${student.id}/profile`);
  await expect(page.getByTestId("calls-opt-out")).toContainText("No phone calls");
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  await page.goto(`/it/admin/students/${student.id}/profile`);
  await expect(page.getByTestId("calls-opt-out")).toContainText("The student has asked not to be called");
  await page.request.post("/api/v1/auth/logout");

  // + back on: the notice disappears.
  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await page.goto("/account/profile");
  await callsBox(page).check();
  await saveSettings(page);
  await expect(page.getByText("Notification settings saved.")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/students/${student.id}/profile`);
  await expect(page.getByRole("heading", { name: /^Student record:/ })).toBeVisible();
  await expect(page.getByTestId("calls-opt-out")).toHaveCount(0);
});
