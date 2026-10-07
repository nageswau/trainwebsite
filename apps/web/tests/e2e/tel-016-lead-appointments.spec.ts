import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-016 (DEC-SCOPE-095): an IT telecaller books "IT course counselling" for a lead with no student account (AC1) -- the stage moves to
// Counselling Scheduled (AC2) and a second lead at the same time is refused with the counselor's busy time (AP1). The IT counselor then
// finds the booking under Appointments and confirms it (AP2). Throwaway accounts; phone width has no sideways scroll.
test.describe.configure({ timeout: 150_000 });

async function signIn(page: Page, portal: "it" | "overseas" | "admin", email: string, password: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function accounts(page: Page, stamp: number) {
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E Appt Manager ${stamp}`, email: `tel016-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E Appt Telecaller ${stamp}`, email: `tel016-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `AP-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselor = await post({ role: "counselor", division: "it", full_name: `E2E Appt Counselor ${stamp}`, email: `tel016-c-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await activateWithToken(page.request, counselor.development_welcome_token);
  return { caller, counselor };
}

// Tomorrow 11:00 India time, as a datetime-local value.
const tomorrowAt11 = () => `${new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + 86_400_000))}T11:00`;
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a telecaller books IT course counselling for a lead and the IT counselor confirms it", async ({ page }) => {
  const stamp = Date.now();
  const { caller, counselor } = await accounts(page, stamp);
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const lead = async (name: string, suffix: string) => {
    const created = await page.request.post("/api/v1/telecaller/leads", { data: { name, phone: `9${String(stamp).slice(-8)}${suffix}`, source: "walk_in" } });
    expect(created.status(), await created.text()).toBe(201);
    return (await created.json()).id as string;
  };
  const name = `Appt Lead ${stamp}`;
  const id = await lead(name, "1");

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await page.goto(`/telecaller/leads/${id}`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const section = page.getByRole("region", { name: "Counselling appointments" });
  await expect(section.getByText("No counselling appointments yet.")).toBeVisible();

  await section.getByRole("button", { name: "Book counselling" }).click();
  const form = section.getByRole("form", { name: "Book counselling" });
  await form.getByRole("button", { name: "Book appointment" }).click(); // required fields refused in place, the first focused
  await expect(form.getByText("Choose the appointment type.")).toBeVisible();
  await expect(form.getByLabel("Appointment type")).toBeFocused();
  // AP4: an IT lead offers the IT types only
  await expect(form.getByLabel("Appointment type").locator("option")).toHaveText(["Choose a type", "Career counselling", "IT course counselling"]);
  await form.getByLabel("Appointment type").selectOption({ label: "IT course counselling" });
  await form.getByLabel("Counselor").selectOption({ label: counselor.full_name });
  await form.getByLabel("Date and time (IST)").fill(tomorrowAt11());
  await form.getByLabel("Meeting link").fill("https://meet.example.com/tel016");
  await form.getByLabel("Purpose").fill("Course fit and batch timing");
  await form.getByRole("button", { name: "Book appointment" }).click();

  await expect(section.getByText(/Appointment CAP-\d{6} booked with/)).toBeVisible();
  const card = section.getByRole("article");
  await expect(card.getByText("Scheduled", { exact: true })).toBeVisible();
  await expect(card.getByRole("link", { name: "https://meet.example.com/tel016" })).toHaveAttribute("rel", "noopener noreferrer");
  await expect(page.getByText("Stage: Counselling Scheduled")).toBeVisible(); // AC2
  await expect(section.getByRole("button", { name: "Book counselling" })).toHaveCount(0); // AP5: one open appointment
  await expect(page.getByRole("list", { name: "Lead activity" }).getByText(/→ Counselling Scheduled/)).toBeVisible(); // the system event

  // AP1: another lead at the same time with the same counselor is refused, naming the busy time
  const second = await lead(`Appt Lead B ${stamp}`, "2");
  await page.goto(`/telecaller/leads/${second}`);
  const other = page.getByRole("region", { name: "Counselling appointments" });
  await other.getByRole("button", { name: "Book counselling" }).click();
  const otherForm = other.getByRole("form", { name: "Book counselling" });
  await otherForm.getByLabel("Appointment type").selectOption({ label: "Career counselling" });
  await otherForm.getByLabel("Counselor").selectOption({ label: counselor.full_name });
  await otherForm.getByLabel("Date and time (IST)").fill(tomorrowAt11());
  await otherForm.getByRole("button", { name: "Book appointment" }).click();
  await expect(otherForm.getByRole("alert")).toContainText("The counselor already has an appointment at this time. Busy:");
  await expect(otherForm.getByLabel("Date and time (IST)")).toBeFocused();
  expect(consoleErrors.filter((e) => !/409|Conflict/.test(e))).toEqual([]);

  // The IT counselor confirms it from Appointments (AP2, AP14)
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.getByRole("link", { name: "Appointments" }).click();
  await page.waitForURL("**/it/counselor/appointments");
  await expect(page.getByRole("heading", { name: "Lead appointments" })).toBeVisible();
  const booking = page.getByRole("article").filter({ hasText: name });
  await expect(booking.getByText("IT course counselling")).toBeVisible();
  await expect(booking.getByRole("button", { name: "Mark completed" })).toHaveCount(0); // AP9: not started yet
  await booking.getByRole("button", { name: "Confirm" }).click();
  await expect(booking.getByText("Appointment confirmed.")).toBeVisible();
  await expect(booking.getByText("Confirmed", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Lead appointments" })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
