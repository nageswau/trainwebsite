import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-012 (DEC-SCOPE-098, AC1 / AC6): the real beat + worker. A meeting booked ~30 minutes ahead gets its "Appointment in 1 hour"
// reminder on the next 5-minute run; the notice opens the appointment. The email buttons' links open the matching dialog only after
// sign-in and never act by themselves; an unknown action is ignored; a signed-out visitor is sent to sign in.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/bdm/my-day");
}

type Notice = { title: string; body: string; action_url: string | null };

test("BDM reminders: the beat job reminds 1 hour ahead; reminder links open the right dialog", async ({ page }) => {
  test.setTimeout(480_000); // the beat runs every 5 minutes
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm012-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm012-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E12-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, bdm.email);
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Reminder College ${stamp}`, city: "Vijayawada", contacts: [{ name: "Mr. XYZ", designation: "Principal", phone: "9876500000", is_primary: true }] },
  })).json()).organization;
  const starts = new Date(Math.ceil(Date.now() / 60_000) * 60_000 + 30 * 60_000).toISOString();
  const booked = await page.request.post("/api/v1/bdm/appointments", {
    data: { organization_id: org.id, contact_id: org.contacts[0].id, starts_at: starts, appointment_type: "college_meeting", location: "Main block", duration_minutes: 60 },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appt = (await booked.json()).appointment;

  // AC1: the next beat run creates the hour-before reminder (organization, time, location; no phone).
  let reminder: Notice | undefined;
  await expect.poll(async () => {
    const notices: Notice[] = await (await page.request.get("/api/v1/workflows/notifications")).json();
    reminder = notices.find((n) => n.title === "Appointment in 1 hour" && n.action_url === `/bdm/appointments/${appt.id}`);
    return !!reminder;
  }, { timeout: 420_000, intervals: [10_000] }).toBe(true);
  expect(reminder!.body).toContain(`Your appointment with ${org.name} is at`);
  expect(reminder!.body).toContain("Location: Main block.");
  expect(reminder!.body).not.toContain("9876500000");

  // The in-app notice opens the appointment.
  await page.goto("/bdm/notifications");
  await page.getByRole("link", { name: /Appointment in 1 hour/ }).first().click();
  await page.waitForURL(`**/bdm/appointments/${appt.id}`);

  // AC6: the email buttons. Reschedule and Cancel open their form; Confirm only focuses its button; ?action is dropped.
  await page.goto(`/bdm/appointments/${appt.id}?action=reschedule`);
  await expect(page.getByLabel("New date and time (IST) (required)")).toBeFocused();
  await expect(page).toHaveURL(new RegExp(`/bdm/appointments/${appt.id}$`));
  await page.reload();
  await expect(page.getByLabel("New date and time (IST) (required)")).toHaveCount(0);

  await page.goto(`/bdm/appointments/${appt.id}?action=cancel`);
  await expect(page.getByRole("button", { name: "Yes, cancel it" })).toBeVisible();

  await page.goto(`/bdm/appointments/${appt.id}?action=confirm`);
  await expect(page.getByRole("button", { name: "Confirm" })).toBeFocused();
  await expect(page.getByRole("status").first()).toContainText("Check the details, then select Confirm.");
  await expect(page.getByText("Scheduled", { exact: true })).toBeVisible(); // nothing was confirmed by the link
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible();

  await page.goto(`/bdm/appointments/${appt.id}?action=confirm`);
  await expect(page.getByRole("status").first()).toContainText("This appointment is already confirmed.");
  await page.goto(`/bdm/appointments/${appt.id}?action=delete`);
  await expect(page.getByRole("button", { name: "Reschedule" })).toHaveAttribute("aria-expanded", "false");

  // Phone width: the opened form fits without sideways scroll.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/bdm/appointments/${appt.id}?action=reschedule`);
  await expect(page.getByLabel("New date and time (IST) (required)")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.setViewportSize({ width: 1280, height: 800 });

  // Signed out, a reminder link leads to sign-in first, then back to the same dialog (the link carries no token).
  await page.request.post("/api/v1/auth/logout");
  await page.context().clearCookies();
  await page.goto(`/bdm/appointments/${appt.id}?action=cancel`);
  await expect(page.getByRole("heading", { name: "BDM sign-in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Yes, cancel it" })).toHaveCount(0);
  await page.getByRole("link", { name: "College BDM" }).click();
  await page.fill("#login-email", bdm.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**/bdm/appointments/${appt.id}`);
  await expect(page.getByRole("button", { name: "Yes, cancel it" })).toBeVisible();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible(); // still nothing done by the link
});
