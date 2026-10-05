import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-007 (AC1, AC3-AC6): a College BDM's past appointment shows as "Outcome pending" (list filter + badge); Complete files the meeting
// report (Interested, next action "Send proposal", a follow-up date) and creates the follow-up; the author edits it the same day; the
// manager reads it with no edit; the report form fits a phone. The API never accepts a past start, so the journey books ~2 minutes
// ahead and waits (the bdm-006 spec's approach).

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** An IST calendar date `days` from today, as YYYY-MM-DD. */
function istDate(days: number): string {
  return new Date(Date.now() + 330 * 60_000 + days * 86_400_000).toISOString().slice(0, 10);
}

test("BDM meeting report: pending, file with follow-up, same-day edit, manager read-only, phone width", async ({ page }) => {
  test.setTimeout(300_000); // includes waiting for the start time to pass
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm007-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm007-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E7-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Report College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;
  const startsAt = Math.ceil(Date.now() / 60_000) * 60_000 + 2 * 60_000;
  const appt = (await (await page.request.post("/api/v1/bdm/appointments", {
    data: { organization_id: org.id, contact_id: org.contacts[0].id, starts_at: new Date(startsAt).toISOString(), appointment_type: "college_meeting" },
  })).json()).appointment;
  await page.waitForTimeout(Math.max(0, startsAt - Date.now() + 2_000));

  // AC5: the list's "Outcome pending" filter finds it, labelled in text.
  await page.goto("/bdm/appointments");
  await page.getByLabel("Status").selectOption("outcome_pending");
  const row = page.getByRole("row", { name: new RegExp(appt.code) });
  await expect(row).toContainText("Outcome pending");
  await row.getByRole("link", { name: appt.code }).click();
  await page.waitForURL(`**/bdm/appointments/${appt.id}`);

  // Phone width: the report form has no horizontal page scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Complete" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  // AC1 + AC3: file the report with a follow-up date; the appointment completes and the follow-up exists.
  await page.getByLabel("Outcome (required)").selectOption("interested");
  await page.getByLabel("Discussion (required)").fill("Principal keen on IT training.\nWants a fee proposal.");
  await page.getByLabel("Next action").fill("Send proposal");
  await page.getByLabel("Responsible person").fill("Mrs Rao");
  await page.getByLabel("Next follow-up (IST date)").fill(istDate(3));
  await page.getByRole("button", { name: "Save report and complete" }).click();
  const report = page.getByRole("region", { name: "Meeting report" });
  await expect(report).toContainText("Send proposal");
  await expect(report).toContainText("Mrs Rao");
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  const detail = (await (await page.request.get(`/api/v1/bdm/appointments/${appt.id}`)).json()).appointment;
  expect(detail.follow_up).toMatchObject({ due_on: istDate(3), status: "open" });
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC4: the author edits the report the same day.
  await page.getByRole("button", { name: "Edit report" }).click();
  await page.getByLabel("Next action").fill("Send proposal and MoU draft");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").first()).toContainText("Meeting report saved.");
  await expect(report).toContainText("Send proposal and MoU draft");

  // The manager reads the report, with no edit.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto(`/bdm/manager/appointments/${appt.id}`);
  await expect(page.getByRole("region", { name: "Meeting report" })).toContainText("Send proposal and MoU draft");
  await expect(page.getByRole("button", { name: "Edit report" })).toHaveCount(0);
});
