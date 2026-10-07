import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-023 (AC1-AC4, edge case, negative scenario): a new manager's dashboard shows the 8 tiles and no alerts; after their BDM books a
// meeting in the next 24 h, "Appointment not confirmed" lists it with a text status word and links to it; confirming it removes the
// alert; a BDM is refused; super_admin narrows to that manager's team; phone and tablet widths show no sideways scroll.

async function superAdmin(page: Page) {
  await page.request.post("/api/v1/auth/logout");
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

const TILES = ["Total BDMs", "Today's Appointments", "Upcoming Appointments", "BDMs Travelling", "Trips This Month", "Meetings Completed",
  "MoUs in Progress", "MoUs Signed"];

test("management dashboard: tiles, an alert that links to its record and clears when resolved, roles, widths", async ({ page }) => {
  test.setTimeout(90_000); // seven sign-ins
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm023-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm023-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E23-${stamp}`, territory: "Kochi", reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  // Edge case: a fresh team -- the 8 tiles in source order, one active BDM, no alerts.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  const overview = page.getByRole("region", { name: "BDM overview" });
  await expect(overview.locator(".kpi-tile dt")).toHaveText(TILES);
  const tile = (label: string) => overview.locator(".kpi-tile", { has: page.getByText(label, { exact: true }) }).locator("dd.kpi-value");
  await expect(tile("Total BDMs")).toHaveText("1");
  await expect(page.getByRole("region", { name: "Alerts" }).getByText("No alerts right now.")).toBeVisible();

  // The BDM books a meeting about two hours ahead (15-minute aligned): an AL-1 "not confirmed" alert.
  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const college = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Dash College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;
  const startsAt = new Date(Math.ceil((Date.now() + 2 * 3_600_000) / 900_000) * 900_000).toISOString();
  const booked = await page.request.post("/api/v1/bdm/appointments", {
    data: { organization_id: college.id, contact_id: college.contacts[0].id, starts_at: startsAt, appointment_type: "college_meeting" },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appointment = (await booked.json()).appointment;

  // Negative scenario: a BDM opening the manager dashboard is refused.
  await page.goto("/bdm/manager/dashboard");
  await expect(page.getByText("BDM manager role required")).toBeVisible();

  // AC1 / AC4: the alert, its text status word, the BDM and time, and the link to the record.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  const alert = page.getByRole("region", { name: /Appointment not confirmed: 1/ });
  await expect(alert.locator(".status.pending")).toHaveText("Attention");
  await expect(alert.getByText(new RegExp(`^E2E BDM ${stamp} · Starts `))).toBeVisible();
  const link = alert.getByRole("link", { name: `${appointment.code} · ${college.name}` });
  await expect(link).toHaveAttribute("href", `/bdm/manager/appointments/${appointment.id}`);
  await link.click();
  await page.waitForURL(`**/bdm/manager/appointments/${appointment.id}`);
  await expect(page.getByText(college.name).first()).toBeVisible();

  // Responsive: no sideways scroll on a phone or a tablet.
  await page.goto("/bdm/manager/dashboard");
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 800 });
    await page.reload();
    await expect(page.getByRole("region", { name: "BDM overview" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC2: once the BDM confirms the meeting, the alert is gone.
  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const confirmed = await page.request.post(`/api/v1/bdm/appointments/${appointment.id}/confirm`);
  expect(confirmed.status(), await confirmed.text()).toBe(200);
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await expect(page.getByRole("region", { name: "Alerts" }).getByText("No alerts right now.")).toBeVisible();

  // R2: super_admin narrows to this manager's team from the admin sidebar's dashboard.
  await superAdmin(page);
  await page.goto(`/bdm/manager/dashboard?manager=${manager.id}`);
  await expect(page.getByRole("heading", { name: `E2E Manager ${stamp}'s team` })).toBeVisible();
  await expect(tile("Total BDMs")).toHaveText("1");
  await expect(page.getByRole("link", { name: "BDM Dashboard" })).toBeVisible();
});
