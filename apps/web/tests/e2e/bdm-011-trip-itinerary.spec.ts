import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-011 (AC1, AC2, AC4; DEC-SCOPE-083): a College BDM plans tomorrow's Hyderabad -> Vijayawada trip with three meetings (EVID-016 §4),
// links one from the booking form's Trip choice, and sees them under the trip with its productivity figures; a date outside the trip
// offers no trip; the manager sees the same itinerary; the report waits for completion; the trip page fits a phone.

test.describe.configure({ timeout: 120_000 });

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
  await page.waitForURL((url) => url.pathname.startsWith(landing)); // the portal home may redirect within it (e.g. /bdm/my-day)
}

/** India's calendar date `days` from today (YYYY-MM-DD). */
const istDay = (days: number) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000));

test("BDM trip: link appointments, itinerary and productivity, manager view, report gate, phone", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm011-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm011-b-${stamp}@example.local`,
      bdm_profile: { bdm_type: "college", employee_id: `E2E11-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  await activateWithToken(page.request, bdm.development_welcome_token);
  await activateWithToken(page.request, manager.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm");
  const org = async (name: string) =>
    (await (await page.request.post("/api/v1/bdm/organizations", {
      data: { org_type: "college", name: `${name} ${stamp}`, city: "Vijayawada", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
    })).json()).organization;
  const [abc, xyz, pqr] = [await org("ABC College"), await org("XYZ College"), await org("PQR College")];
  const day = istDay(1);
  const trip = await (await page.request.post("/api/v1/bdm/trips", {
    data: { travel_date: day, return_date: day, from_place: "Hyderabad", to_place: "Vijayawada", purpose: "College Marketing", mode: "train", estimated_cost: "2500.00" },
  })).json();
  const book = async (o: { id: string; contacts: { id: string }[] }, time: string, type: string, extra: Record<string, unknown> = {}) =>
    (await (await page.request.post("/api/v1/bdm/appointments", {
      data: { organization_id: o.id, contact_id: o.contacts[0].id, starts_at: `${day}T${time}:00+05:30`, appointment_type: type, trip_id: trip.id, ...extra },
    })).json()).appointment;
  const first = await book(abc, "10:00", "course_promotion", { expected_leads: 40, expected_revenue: "50000" });
  const second = await book(xyz, "13:00", "mou_discussion", { expected_leads: 20 });
  for (const a of [first, second]) await page.request.post(`/api/v1/bdm/appointments/${a.id}/confirm`);

  // AC1 in the UI: a date outside the trip offers no trip; the trip's own day offers it, and booking links it.
  await page.goto(`/bdm/appointments/new?organization=${pqr.id}`, { waitUntil: "networkidle" });
  await page.getByLabel("Date and time (IST) (required)").fill(`${istDay(5)}T16:00`);
  await expect(page.getByText("None of your open trips covers this date.")).toBeVisible();
  await page.getByLabel("Date and time (IST) (required)").fill(`${day}T16:00`);
  await page.getByLabel("Type (required)").selectOption("principal_meeting");
  await page.getByLabel("Trip").selectOption(trip.id);
  await page.getByRole("button", { name: "Book appointment" }).click();
  await page.waitForURL(/\/bdm\/appointments\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("link", { name: new RegExp(trip.code) })).toHaveAttribute("href", `/bdm/travel/${trip.id}#trip-appointments`);

  // AC4: the §4 table -- time, organization, meeting, status -- and AC2's figures.
  await page.goto(`/bdm/travel/${trip.id}#trip-appointments`);
  const table = page.getByRole("table", { name: "Appointments on this trip" });
  await expect(table.getByRole("row")).toHaveCount(4);
  await expect(table.getByRole("row").nth(1)).toContainText(/10:00 am.*ABC College.*Course Promotion.*Confirmed/);
  await expect(table.getByRole("row").nth(2)).toContainText(/1:00 pm.*XYZ College.*MoU Discussion.*Confirmed/);
  await expect(table.getByRole("row").nth(3)).toContainText(/4:00 pm.*PQR College.*Principal Meeting.*Scheduled/);
  const tile = (label: string) => page.locator(".kpi-tile", { has: page.getByText(label, { exact: true }) });
  await expect(tile("Meetings planned")).toContainText("3");
  await expect(tile("Meetings completed")).toContainText("0");
  await expect(tile("Expected leads")).toContainText("60");
  await expect(tile("Expected revenue")).toContainText("₹50,000.00");
  await expect(tile("Actual revenue")).toContainText("Not tracked yet");
  await expect(page.getByRole("note").first()).toContainText("Trip not approved yet");
  for (const id of ["trip-appointments", "trip-costs", "trip-remarks"]) await expect(page.locator(`section#${id}`)).toHaveCount(1);

  // AC3: no report before completion.
  await page.goto(`/bdm/travel/${trip.id}/report`);
  await expect(page.getByRole("status")).toContainText("The travel report is available once the trip is completed");

  // The trip page fits a phone (the itinerary scrolls inside its own region).
  await page.goto(`/bdm/travel/${trip.id}`);
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(table).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.setViewportSize({ width: 1280, height: 800 });

  // The manager sees the same itinerary on the team trip.
  await signIn(page, "admin", manager.email, "/bdm/manager");
  await page.goto(`/bdm/manager/trips/${trip.id}`);
  await expect(page.getByRole("table", { name: "Appointments on this trip" }).getByRole("row")).toHaveCount(4);
  await expect(page.getByRole("link", { name: `ABC College ${stamp}` })).toHaveAttribute("href", `/bdm/manager/appointments/${first.id}`);
});
