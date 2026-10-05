import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-006 (AC1-AC7): a College BDM books from the organization page, confirms, reschedules (the history keeps the old time), waits for
// the start time and completes with an outcome; an archived organization offers no booking; the manager sees the appointment read-only;
// the list fits a phone. The API never accepts a past start (A7), so the journey books ~2 minutes ahead and waits (plan refinement 4).

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

/** A datetime-local value in IST `minutes` after the next whole minute, and that instant in ms. */
function istSlot(minutes: number): { input: string; at: number } {
  const at = Math.ceil(Date.now() / 60_000) * 60_000 + minutes * 60_000;
  return { input: new Date(at + 330 * 60_000).toISOString().slice(0, 16), at };
}

test("BDM appointments: book, confirm, reschedule, complete; archived org; manager read-only", async ({ page }) => {
  test.setTimeout(300_000); // includes waiting for the start time to pass
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm006-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm006-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E6-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const newOrg = async (name: string) =>
    (await (await page.request.post("/api/v1/bdm/organizations", { data: { org_type: "college", name, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] } })).json()).organization;
  const org = await newOrg(`E2E College ${stamp}`);
  const archived = await newOrg(`E2E Closed ${stamp}`);
  await page.request.post(`/api/v1/bdm/organizations/${archived.id}/archive`);

  // AC1: book from the organization page.
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.getByRole("link", { name: "Add appointment" }).click();
  await page.waitForURL(`**/bdm/appointments/new?organization=${org.id}`);
  await expect(page.getByLabel("Contact person (required)")).toHaveValue(org.contacts[0].id);
  const first = istSlot(2);
  await page.getByLabel("Date and time (IST) (required)").fill(first.input);
  await page.getByLabel("Type (required)").selectOption("college_meeting");
  await page.getByLabel("Location").fill("Main block");
  await page.getByRole("button", { name: "Book appointment" }).click();
  await page.waitForURL(/\/bdm\/appointments\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("status").first()).toContainText("booked");
  await expect(page.getByText("Scheduled", { exact: true })).toBeVisible();

  // AC3: confirm, then AC4: reschedule one minute later; the history keeps the old time.
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible();
  const second = istSlot(3);
  await page.getByRole("button", { name: "Reschedule" }).click();
  await page.getByLabel("New date and time (IST) (required)").fill(second.input);
  await page.getByRole("button", { name: "Save new time" }).click();
  await expect(page.getByText("Rescheduled", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "History" })).toContainText("moved from");

  // AC5: after the start time, complete with an outcome (bdm-007: by filing the meeting report).
  await page.waitForTimeout(Math.max(0, second.at - Date.now() + 2_000));
  await page.reload();
  await expect(page.getByRole("note")).toContainText("Outcome pending");
  await page.getByRole("button", { name: "Complete" }).click();
  await page.getByLabel("Outcome (required)").selectOption("interested");
  await page.getByLabel("Discussion (required)").fill("Principal keen on IT training.");
  await page.getByRole("button", { name: "Save report and complete" }).click();
  await expect(page.getByRole("region", { name: "Meeting report" })).toContainText("Interested");
  const code = (await page.locator(".eyebrow").first().textContent())?.split(" · ")[0] ?? "";

  // AC6: an archived organization offers no booking.
  await page.goto(`/bdm/organizations/${archived.id}`);
  await expect(page.getByRole("link", { name: "Add appointment" })).toHaveCount(0);

  // Phone width: no horizontal page scroll on the list (R-F8).
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/bdm/appointments?date_from=");
  await expect(page.getByRole("link", { name: code })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC7: the manager reads it, with no actions.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/appointments?date_from=");
  await page.getByRole("link", { name: code }).click();
  await expect(page.getByRole("region", { name: "History" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Confirm|Reschedule|Complete|Cancel appointment|Edit/ })).toHaveCount(0);
});
