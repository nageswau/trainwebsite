import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-011 (AC1-AC3, F2, F4, F5, F9): follow-ups. A telecaller adds one to their lead (the form's own check, the API's past-time 422 and
// the optional move to Follow-up), finds it on its day, reschedules and completes it; a manager reads the same list without actions;
// closing a lead cancels its open follow-ups. Like tel-008, the lead is assigned through tel-007's API so this run's telecaller has it.
test.describe.configure({ timeout: 150_000 });

const IST_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" });
const istDay = (offsetDays: number) => IST_DAY.format(new Date(Date.now() + offsetDays * 86_400_000));
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E FU Manager ${stamp}`, email: `tel011-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E FU Telecaller ${stamp}`, email: `tel011-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `FU-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const leads: string[] = [];
  for (const [i, name] of [`Follow-up Lead ${stamp}`, `Closing Lead ${stamp}`].entries()) {
    const mobile = `8${String(stamp).slice(-8)}${i}`;
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name, email: `tel011-${i}-${stamp}@example.com`, phone: mobile, subject: "Cyber Security", message: "Call me." },
    });
    expect(created.status()).toBe(201);
    leads.push((await created.json()).id);
  }
  const assigned = await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: leads, telecaller_user_id: caller.id } });
  expect(assigned.status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller, leads };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a telecaller adds, finds, reschedules and completes a follow-up; the manager reads it; closing cancels", async ({ page }) => {
  const stamp = Date.now();
  const { manager, caller, leads } = await setup(page, stamp);
  const name = `Follow-up Lead ${stamp}`;
  const tomorrow = istDay(1);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await expect(page.getByRole("heading", { name: "Today's follow-ups" })).toBeVisible(); // the dashboard card
  await page.goto(`/telecaller/leads/${leads[0]}`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Follow-ups", exact: true }) });
  await expect(section.getByText("No follow-ups yet.")).toBeVisible();

  await section.getByRole("button", { name: "Add follow-up" }).click();
  const form = page.getByRole("form", { name: "Add follow-up" });
  await form.getByRole("button", { name: "Add follow-up" }).click();
  await expect(form.getByText("Choose a due date and time")).toBeVisible();
  await form.getByLabel(/Due date and time/).fill("2026-01-01T09:00"); // in the past: the API's 422 lands on the field (AC3)
  await form.getByLabel("Reason (required)").selectOption("discuss_with_parents");
  await form.getByLabel("Next action").fill("Call today at 4:00 PM");
  await form.getByLabel("Notes").fill("Parents decide by Friday");
  await form.getByRole("button", { name: "Add follow-up" }).click();
  await expect(form.getByText("Choose a due time in the future")).toBeVisible();
  await expect(form.getByLabel("Notes")).toHaveValue("Parents decide by Friday");
  await form.getByLabel(/Due date and time/).fill(`${tomorrow}T16:00`);
  await form.getByLabel("Also move the lead to Follow-up").check();
  await form.getByRole("button", { name: "Add follow-up" }).click();
  await expect(section.getByText("Follow-up added.")).toBeVisible();
  await expect(page.getByText(/Stage: Follow-up · Priority:/)).toBeVisible(); // F5
  await expect(page.getByRole("list", { name: "Lead activity" }).getByRole("listitem").first()).toContainText("Stage: Assigned → Follow-up");
  await expect(section.getByRole("listitem")).toContainText(["Need to discuss with parents"]);
  await expect(section.getByRole("listitem").first()).toContainText("16:00 IST");

  await page.getByRole("link", { name: "Follow-ups", exact: true }).first().click();
  await page.waitForURL("**/telecaller/follow-ups");
  await page.getByLabel("Day").fill(tomorrow);
  await expect(page).toHaveURL(new RegExp(`day=${tomorrow}`));
  const cards = page.getByRole("list", { name: "Follow-ups" }).getByRole("listitem");
  await expect(cards).toHaveCount(1); // AC1: exactly that day's open follow-ups
  await expect(cards.first()).toContainText("Call today at 4:00 PM");
  await expect(cards.first()).toContainText("Warm");
  await cards.first().getByRole("button", { name: "Reschedule" }).click();
  await page.getByRole("form", { name: "Reschedule follow-up" }).getByLabel(/Due date and time/).fill(`${tomorrow}T11:30`);
  await page.getByRole("form", { name: "Reschedule follow-up" }).getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Follow-up rescheduled.")).toBeVisible();
  await expect(cards.first()).toContainText("11:30 IST");
  await page.reload(); // stored, and the day stays in the URL
  await expect(cards.first()).toContainText("11:30 IST");
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page), `no side scroll at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // F9: My Leads narrows to leads with a follow-up due today (none here: it is tomorrow's)
  await page.goto(`/telecaller/leads?follow_up=today&q=${encodeURIComponent(name)}`);
  await expect(page.getByText("No leads match these filters.")).toBeVisible();

  // F2: the manager reads the same list, with the telecaller's name and no actions
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.goto(`/telecaller/manager/follow-ups?day=${tomorrow}`);
  const managed = page.getByRole("list", { name: "Follow-ups" }).getByRole("listitem");
  await expect(managed).toHaveCount(1);
  await expect(managed.first()).toContainText(`E2E FU Telecaller ${stamp}`);
  await expect(managed.first().getByRole("button")).toHaveCount(0);

  // the telecaller completes it; closing the second lead cancels its follow-up (F4)
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.goto(`/telecaller/follow-ups?day=${tomorrow}`);
  await cards.first().getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Marked done.")).toBeVisible();
  await expect(page.getByText("No follow-ups due on this day.")).toBeVisible();

  const second = await page.request.post(`/api/v1/telecaller/leads/${leads[1]}/follow-ups`, {
    data: { due_at: new Date(Date.now() + 2 * 86_400_000).toISOString(), reason: "comparing_courses" },
  });
  expect(second.status()).toBe(201);
  const closed = await page.request.post(`/api/v1/telecaller/leads/${leads[1]}/stage`, { data: { to_stage: "not_interested", reason: "Joined elsewhere" } });
  expect(closed.status()).toBe(200);
  await page.goto(`/telecaller/leads/${leads[1]}`);
  await expect(section.getByRole("listitem").first()).toContainText("Lead closed");
  await expect(section.getByRole("button", { name: "Add follow-up" })).toHaveCount(0);

  // the one expected error: the browser logs the 422 of the past-time save
  expect(consoleErrors.filter((text) => !text.includes("422"))).toEqual([]);
});
