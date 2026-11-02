import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-025 (DEC-SCOPE-347): the IT Admin changes a batch's schedule; its active student and the student's IT counselor are each told
// once, with a "Changed: timetable." summary, and the counselor's new Notifications page opens the counselor timetable. A fresh batch,
// student and counselor are created per run, so reruns on one database never collide.
test.describe.configure({ timeout: 150_000 });

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function ok(response: Awaited<ReturnType<Page["request"]["post"]>>, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

test("a batch schedule change reaches the student and their IT counselor once each", async ({ page }) => {
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  const user = async (role: string, name: string) => {
    const created = await ok(await page.request.post("/api/v1/admin/users", { data: { role, division: "it", full_name: name, email: `itc025-${role}-${stamp}@example.local` } }), 201);
    await activateWithToken(page.request, created.development_welcome_token);
    return created;
  };
  const counselor = await user("counselor", `Itc025 Counselor ${stamp}`);
  const student = await user("it_student", `Itc025 Student ${stamp}`);
  const programs = (await (await page.request.get("/api/v1/admin/batches")).json()) as { program_id: string }[];
  const today = new Date().toISOString().slice(0, 10);
  const later = new Date(Date.now() + 60 * 86_400_000).toISOString().slice(0, 10);
  const batch = await ok(await page.request.post("/api/v1/admin/batches", {
    data: { program_id: programs[0].program_id, name: `ITC025-${stamp}`, start_date: today, end_date: later, schedule: "Mon/Wed 7-9 pm", status: "active" },
  }), 201);
  const enrolment = await ok(await page.request.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batch.id, student_id: student.id } }), 201);
  await ok(await page.request.post(`/api/v1/admin/enrollments/${enrolment.id}/approve`));
  await ok(await page.request.put(`/api/v1/admin/it/students/${student.id}/counselor`, { data: { counselor_id: counselor.id } }));

  // The batch edit has no screen of its own (API only); a no-op save first, then a real change.
  await ok(await page.request.patch(`/api/v1/admin/batches/${batch.id}`, { data: { schedule: "Mon/Wed 7-9 pm", capacity: 20 } }));
  await ok(await page.request.patch(`/api/v1/admin/batches/${batch.id}`, { data: { schedule: "Tue/Thu 6-8 pm" } }));

  await signIn(page, counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.getByRole("navigation").getByRole("link", { name: "Notifications" }).first().click();
  await page.waitForURL("**/it/counselor/notifications");
  const notice = page.getByText("Student's batch updated", { exact: true });
  await expect(notice).toHaveCount(1); // one notice, and the no-op save sent none
  await expect(page.getByText(/Changed: timetable\.$/)).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("link", { name: "Open" }).first().click();
  await page.waitForURL("**/it/counselor/timetable");

  await signIn(page, student.email, E2E_PASSWORD, "/it/student/dashboard");
  await page.goto("/it/student/notifications");
  await expect(page.getByText("Course or batch updated", { exact: true })).toHaveCount(1);
  await expect(page.getByText(/Changed: timetable\.$/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
