import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-014 (AC1, AC2, AC3, edge case, negative scenario): a new College BDM lands on an empty My Day with calls to action; after booking
// today's meetings, an upcoming trip with a linked meeting and follow-ups, My Day shows the §15 sections and the College tiles, with
// MoU follow-ups "not tracked"; a phone shows no sideways scroll; the manager opening My Day is sent to the manager dashboard.

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

const IST_MS = 330 * 60_000;
const istDate = (ms: number) => new Date(ms + IST_MS).toISOString().slice(0, 10);
const istTime = (ms: number) => new Date(ms + IST_MS).toISOString().slice(11, 16);
const timeText = (ms: number) => new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });

test("My Day: empty state, the §15 sections and College tiles, phone width, manager redirect", async ({ page }) => {
  // Two meetings later today (IST), 15-minute aligned; the API refuses a past time, so this skips in the last two hours before midnight.
  const first = Math.ceil((Date.now() + 30 * 60_000) / (15 * 60_000)) * 15 * 60_000;
  const second = first + 90 * 60_000; // past the first (60 min) so the overlap guard stays quiet
  const today = istDate(Date.now());
  test.skip(istDate(second) !== today, "too close to midnight IST to book two meetings today");

  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm014-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm014-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E14-${stamp}`, territory: "Kochi", reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  // Edge case: a new BDM sees empty sections with calls to action, and the untracked tile labelled (AC3).
  await signIn(page, "it", bdm.email, "/bdm/my-day");
  await expect(page.getByRole("heading", { name: "Today's appointments: 0" })).toBeVisible();
  await expect(page.getByText(`Employee ID E2E14-${stamp} · Kochi`)).toBeVisible();
  await expect(page.getByRole("link", { name: "Book an appointment" })).toHaveAttribute("href", "/bdm/appointments/new");
  await expect(page.getByRole("link", { name: "Plan a trip" })).toHaveAttribute("href", "/bdm/travel/new");
  await expect(page.getByText("No follow-ups due.")).toBeVisible();
  const overview = page.getByRole("region", { name: "College overview" });
  await expect(overview.locator(".kpi-tile")).toHaveCount(8);
  await expect(overview.locator(".kpi-tile", { hasText: "MoU follow-ups" })).toContainText("Not tracked yet");

  // Data through the API, as the BDM would enter it.
  const org = async (orgType: string, name: string) => (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: orgType, name: `${name} ${stamp}`, city: "Vijayawada", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;
  const college = await org("college", "E2E MyDay College");
  const agent = await org("agent", "E2E MyDay Agency");
  const tripDay = istDate(Date.now() + 3 * 86_400_000);
  const trip = await page.request.post("/api/v1/bdm/trips", {
    data: { travel_date: tripDay, return_date: tripDay, from_place: "Kochi", to_place: "Vijayawada", purpose: "Visits", mode: "train", estimated_cost: "1000.00" },
  });
  expect(trip.status(), await trip.text()).toBe(201);
  const tripId = (await trip.json()).id;
  const appt = (startsAt: string, type: string, extra: Record<string, unknown> = {}) => page.request.post("/api/v1/bdm/appointments", {
    data: { organization_id: college.id, contact_id: college.contacts[0].id, starts_at: startsAt, appointment_type: type, ...extra },
  });
  const task = (orgId: string) => page.request.post("/api/v1/bdm/tasks", { data: { kind: "follow_up", title: "Call back", due_on: today, organization_id: orgId } });
  for (const response of [
    await appt(`${today}T${istTime(first)}:00+05:30`, "placement_cell_meeting"),
    await appt(`${today}T${istTime(second)}:00+05:30`, "course_promotion"),
    await appt(`${tripDay}T11:00:00+05:30`, "college_meeting", { trip_id: tripId }),
    await task(college.id), await task(college.id), await task(agent.id),
  ]) expect(response.status(), await response.text()).toBe(201);

  // AC1 / AC2: the §15 sections and the College tiles from the real data.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Today's appointments: 2" })).toBeVisible();
  await expect(page.getByRole("link", { name: `${timeText(first)} — ${college.name}` })).toHaveAttribute("href", /\/bdm\/appointments\//);
  await expect(page.getByRole("link", { name: `${timeText(second)} — ${college.name}` })).toBeVisible();
  const travel = page.getByRole("region", { name: "Upcoming travel" });
  await expect(travel.getByRole("link", { name: /— Kochi → Vijayawada$/ })).toHaveAttribute("href", `/bdm/travel/${tripId}`);
  await expect(travel.getByText("1 appointment scheduled")).toBeVisible();
  const followUps = page.getByRole("region", { name: "Follow-ups" });
  await expect(followUps.getByText("2 College follow-ups")).toBeVisible();
  await expect(followUps.getByText("1 Agent follow-up")).toBeVisible();
  const tile = (label: string) => overview.locator(".kpi-tile", { has: page.getByText(label, { exact: true }) }).locator("dd");
  await expect(tile("College meetings")).toHaveText("2");
  await expect(tile("Placement-cell meetings")).toHaveText("1");
  await expect(tile("Course promotion activities")).toHaveText("1");
  await expect(tile("Seminars")).toHaveText("0");

  // Responsive: no sideways scroll on a phone or a tablet.
  for (const width of [320, 768]) {
    await page.setViewportSize({ width, height: 800 });
    await page.reload();
    await expect(page.getByRole("heading", { name: "Today's appointments: 2" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }

  // Negative scenario: a manager hitting My Day lands on the manager dashboard.
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto("/bdm/my-day");
  await page.waitForURL("**/bdm/manager/dashboard");
});
