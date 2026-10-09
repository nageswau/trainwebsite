import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-009 (AC1-AC3, P1, E1): a partnership manager schedules an MoU discussion from the university page with two university participants
// (the university moves to Meeting Scheduled), sees the missing-link warning of an online meeting, reschedules it (history keeps both
// times), and the list fits a phone. A second test records an outcome once a meeting has started: its next action and next meeting date
// become follow-ups (AC2, Q-12) and the university moves to Meeting Completed. The API refuses a past start, so that meeting is scheduled
// two minutes ahead and the test waits for it. Throwaway accounts via the real admin API.

const istInput = (ms: number) => new Date(ms + 330 * 60_000).toISOString().slice(0, 16); // YYYY-MM-DDTHH:mm in IST
const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/partnership/dashboard");
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc009-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc009-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U09-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Meetings University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  const { contact: priya } = await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "Priya Raman", designation: "Director" });
  await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "James Hart", designation: "Head of Admissions" });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, university, priya };
}

async function stageOf(page: Page, universityId: string): Promise<string> {
  return (await (await page.request.get(`/api/v1/partnership/universities/${universityId}`)).json()).university.pipeline.stage;
}

test("an MoU discussion is scheduled with two university participants, then rescheduled", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { manager, university } = await setUp(page, stamp);
  await signIn(page, manager.email);

  await page.getByRole("link", { name: "Meetings", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "University meetings" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Upcoming/ })).toHaveAttribute("aria-current", "page");

  await page.goto(`/partnership/universities/${university.id}`);
  const section = page.getByRole("region", { name: "Meetings", exact: true });
  await expect(section.getByText("No meetings scheduled yet.")).toBeVisible();
  await section.getByRole("link", { name: "Schedule a meeting" }).click();
  await expect(page.getByRole("heading", { name: "Schedule a university meeting" })).toBeVisible();
  await page.getByRole("button", { name: "Schedule meeting" }).click();
  await expect(page.getByText("Choose the meeting type")).toBeVisible();
  await expect(page.getByText("Choose the date and time")).toBeVisible();

  await page.getByLabel("Meeting type").selectOption("mou_discussion");
  await page.getByLabel("Date and time (IST)").fill(`${inDays(3)}T10:00`);
  await page.getByLabel("Online", { exact: true }).check();
  await expect(page.getByText(/has no link yet/)).toBeVisible(); // E1: a warning, not a block
  await page.getByLabel("Contact person").selectOption({ label: "Priya Raman" });
  await expect(page.getByText("Designation: Director")).toBeVisible();
  await page.getByLabel("James Hart").check();
  await page.getByLabel("Agenda").fill("1. MoU clauses\n2. September intake");
  await page.getByRole("button", { name: "Schedule meeting" }).click();
  await page.waitForURL(/\/partnership\/meetings\/[0-9a-f-]{36}$/);
  const detail = page.url();

  // AC1 / P1: the record, both sides, the warning and the history.
  await expect(page.getByRole("heading", { name: `MoU discussion with ${university.name}` })).toBeVisible();
  await expect(page.getByRole("note").filter({ hasText: "has no link yet" })).toBeVisible();
  const facts = page.getByRole("region", { name: "Meeting", exact: true });
  await expect(facts.getByText("Priya Raman (Director)").first()).toBeVisible();
  await expect(facts.getByText(/James Hart \(Head of Admissions\)/)).toBeVisible();
  await expect(facts.getByText(`E2E Manager ${stamp}`).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Record outcome" })).toHaveCount(0); // not started yet
  await expect(page.getByText(/once the meeting has started/)).toBeVisible();
  expect(await stageOf(page, university.id)).toBe("meeting_scheduled"); // AC3

  // Reschedule: the history keeps the old and new times.
  await page.getByRole("link", { name: "Edit" }).click();
  await page.getByLabel("Date and time (IST)").fill(`${inDays(4)}T15:30`);
  await page.getByLabel("Reason for the new time (optional)").fill("Dean travelling");
  await page.getByLabel("Meeting link").fill("https://meet.example.com/mou");
  await page.getByRole("button", { name: "Save meeting" }).click();
  await page.waitForURL(detail);
  const history = page.getByRole("region", { name: "History" });
  await expect(history.getByText("Rescheduled")).toBeVisible();
  await expect(history.getByText("Dean travelling")).toBeVisible();
  await expect(page.getByText(/has no link yet/)).toHaveCount(0);

  // The university page lists it; the list fits a phone without sideways scrolling.
  await page.goto(`/partnership/universities/${university.id}`);
  await expect(section.getByRole("link", { name: /^UMT-\d{6}$/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/partnership/meetings?view=upcoming");
  await expect(page.getByRole("heading", { name: "University meetings" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("an outcome's next action and next meeting date become follow-ups", async ({ page }) => {
  test.setTimeout(300_000);
  const stamp = Date.now();
  const { manager, university, priya } = await setUp(page, stamp);
  await signIn(page, manager.email);
  const start = istInput(Date.now() + 120_000); // the earliest start the API accepts that a test can wait for
  const response = await page.request.post("/api/v1/partnership/meetings", {
    data: { university_id: university.id, meeting_type: "partnership_discussion", starts_at: `${start}:00+05:30`, mode: "offline", contact_id: priya.id },
  });
  expect(response.status(), await response.text()).toBe(201);
  const { meeting } = await response.json();
  await page.goto(`/partnership/meetings/${meeting.id}`);
  await expect(async () => {
    await page.reload();
    await expect(page.getByRole("button", { name: "Record outcome" })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 200_000, intervals: [10_000] });

  await page.getByRole("button", { name: "Record outcome" }).click();
  await page.getByRole("button", { name: "Save outcome" }).click();
  await expect(page.getByText("Record notes, discussion points or decisions")).toBeVisible();
  await page.getByLabel("Discussion points").fill("Commission and intakes");
  await page.getByLabel("Decisions").fill("Proceed to a proposal");
  await page.getByLabel("Next action", { exact: true }).fill("Send the partnership proposal");
  await page.getByLabel("Next action due date").fill(inDays(2));
  await page.getByLabel("Next meeting date").fill(inDays(30));
  await page.getByRole("button", { name: "Save outcome" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Outcome recorded." })).toBeVisible();
  const outcome = page.getByRole("region", { name: "Outcome" });
  await expect(outcome.getByText("Proceed to a proposal")).toBeVisible();
  await expect(outcome.getByText(/Send the partnership proposal · due/)).toBeVisible(); // AC2
  await expect(outcome.getByText(/Schedule the next meeting · due/)).toBeVisible(); // Q-12
  expect(await stageOf(page, university.id)).toBe("meeting_completed"); // MG13

  await page.goto(`/partnership/universities/${university.id}`); // the follow-up is in the university's open follow-ups (upc-020)
  await expect(page.getByRole("region", { name: "Follow-ups & tasks" }).getByText("Send the partnership proposal").first()).toBeVisible();
});
