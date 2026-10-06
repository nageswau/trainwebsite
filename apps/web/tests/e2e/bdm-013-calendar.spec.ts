import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-013 (AC1, AC2, AC4, AC5, AC6): a College BDM's §5 week, built through the API two weeks ahead -- a day trip to Hyderabad with agent
// meetings, a Vijayawada trip with college meetings, the return, a follow-up -- read in the week and day views, at phone width, and by
// the manager.

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

// The Monday two weeks after this IST week's Monday, plus `n` days.
function day(n: number): string {
  const ist = new Date(Date.now() + 330 * 60_000);
  const monday = new Date(Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate() - ((ist.getUTCDay() + 6) % 7) + 14));
  return new Date(monday.getTime() + n * 86_400_000).toISOString().slice(0, 10);
}

test("BDM calendar: the §5 week, day view, phone width, manager read", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm013-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm013-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E13-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Calendar College ${stamp}`, city: "Vijayawada", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;
  const trip = (travel: string, ret: string, to: string) => page.request.post("/api/v1/bdm/trips", {
    data: { travel_date: travel, return_date: ret, from_place: "Kochi", to_place: to, purpose: "Visits", mode: "train", estimated_cost: "1000.00" },
  });
  const appt = (d: string, hour: string, type: string) => page.request.post("/api/v1/bdm/appointments", {
    data: { organization_id: org.id, contact_id: org.contacts[0].id, starts_at: `${d}T${hour}:00+05:30`, appointment_type: type },
  });
  for (const response of [
    await trip(day(0), day(0), "Hyderabad"), await trip(day(1), day(3), "Vijayawada"),
    await appt(day(0), "10:00", "agent_meeting"), await appt(day(0), "15:00", "agent_meeting"),
    await appt(day(1), "11:00", "college_meeting"), await appt(day(2), "11:00", "college_meeting"),
    await page.request.post("/api/v1/bdm/tasks", { data: { kind: "follow_up", title: "Send the MoU draft", due_on: day(4) } }),
  ]) expect(response.status(), await response.text()).toBe(201);

  await page.goto(`/bdm/calendar?view=week&date=${day(2)}`);
  const headings = page.locator("section h4");
  await expect(headings).toHaveCount(7);
  const lines = (await headings.allInnerTexts()).map((t) => t.split(" — ")[1]);
  expect(lines).toEqual(["Hyderabad – Agent Meetings", "Vijayawada – College Meetings", "Vijayawada – College Meetings", "Return travel", "Follow-ups", "Nothing planned", "Nothing planned"]);
  await expect(page.getByRole("link", { name: "Send the MoU draft" })).toHaveAttribute("href", "/bdm/follow-ups");

  // AC5: the controls are links, reached and followed with the keyboard.
  await page.getByRole("link", { name: "Day", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.waitForURL(`**/bdm/calendar?view=day&date=${day(2)}`);
  await expect(page.locator("section h4")).toHaveCount(1);
  await page.getByRole("link", { name: /College Meeting — E2E Calendar College/ }).click();
  await page.waitForURL("**/bdm/appointments/*");

  // AC4: no sideways scroll on a phone.
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(`/bdm/calendar?view=week&date=${day(2)}`);
  await expect(page.getByRole("heading", { name: "Your calendar" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  // AC6: the manager reads the same week; another id is "not on your team".
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto(`/bdm/manager/calendar?view=week&date=${day(2)}&bdm=${bdm.id}`);
  await expect(page.getByRole("heading", { name: `E2E BDM ${stamp}'s calendar` })).toBeVisible();
  await expect(page.locator("section h4").first()).toContainText("Hyderabad – Agent Meetings");
  await page.goto(`/bdm/manager/calendar?bdm=${manager.id}`);
  await expect(page.getByText("This BDM is not on your team.")).toBeVisible();
});
