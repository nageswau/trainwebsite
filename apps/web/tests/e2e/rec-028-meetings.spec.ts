import { expect, test, type Page } from "@playwright/test";

// rec-028 (AC1, AC2; MT5, MT9, MT10): the seeded recruiter schedules a contract discussion with two contacts on a new company, which
// moves it to Meeting Scheduled; the meeting shows under Upcoming; a reschedule keeps its history; the seeded placement manager reads it
// without any write control. AC2 (outcome -> follow-up) needs a started meeting, which the API refuses to create, so it is covered by
// test_rec_028_meetings.py and the component tests.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** An IST wall-clock `datetime-local` value `days` from now at 10:30. */
function istInput(days: number): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000));
  return `${day}T10:30`;
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("meetings on a company: schedule with two contacts moves the stage, Upcoming, reschedule history; the manager reads only", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Rec028 ${Date.now()} Technologies`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new?with=contact");
  await page.getByRole("group", { name: "Recruiter contact" }).getByLabel("Contact name (required)").fill("Priya Sharma");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();
  const companyId = detailUrl.split("/").at(-1);
  expect((await page.request.post(`/api/v1/recruiter/companies/${companyId}/contacts`, { data: { name: "Ravi Kumar" } })).status()).toBe(201);
  await page.reload();

  const pipeline = page.getByRole("region", { name: /pipeline/i }).first();
  await expect(pipeline).toContainText("New Lead");
  const section = page.getByRole("region", { name: "Meetings" });
  await expect(section.getByText("No meetings yet.")).toBeVisible();

  // Positive scenario: a contract discussion with two contacts (the primary plus one more).
  await section.getByRole("button", { name: "Schedule meeting" }).click();
  const form = section.getByRole("form", { name: "Schedule meeting" });
  await form.getByLabel("Meeting type (required)").selectOption({ label: "Contract discussion" });
  await form.getByLabel("Date and time (IST, required)").fill(istInput(2));
  await form.getByLabel("Mode (required)").selectOption("Online");
  await form.getByLabel("Meeting link").fill("https://meet.example.com/rec028");
  await expect(form.getByLabel("Contact")).toContainText("Ravi Kumar");
  await form.getByLabel("Contact").selectOption({ label: "Priya Sharma" });
  await form.getByRole("checkbox", { name: "Ravi Kumar" }).check();
  await form.getByRole("button", { name: "Schedule meeting" }).click();
  await expect(section.getByRole("status")).toContainText("scheduled.");
  const item = section.getByRole("list", { name: "Meetings" }).getByRole("listitem").first();
  await expect(item).toContainText("Contract discussion");
  await expect(item).toContainText("Priya Sharma, Ravi Kumar");
  await expect(item.getByRole("link", { name: /Meeting link/ })).toHaveAttribute("href", "https://meet.example.com/rec028");

  // AC1: the company moved to Meeting Scheduled.
  await expect(page.locator("body")).toContainText("Meeting Scheduled");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/recruiter/companies/${companyId}`)).json()).company.stage).toBe("meeting_scheduled");

  // Edge case: rescheduling keeps the history.
  await item.getByRole("button", { name: "Reschedule / edit" }).click();
  const edit = item.getByRole("form", { name: "Edit meeting" });
  await edit.getByLabel("Date and time (IST, required)").fill(istInput(4));
  await edit.getByLabel("Reason for rescheduling").fill("Client asked to move it");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(section.getByRole("status")).toHaveText("Meeting updated.");
  await expect(item.getByText("History (2)")).toBeVisible();
  await item.getByText("History (2)").click();
  await expect(item).toContainText("Client asked to move it");

  // MT10: it sits in Upcoming.
  await page.goto("/recruiter/meetings");
  await expect(page.getByRole("button", { name: /^Upcoming/ })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("list", { name: "Meetings" }).getByRole("listitem").filter({ hasText: name })).toHaveCount(1);

  // MT9: the manager reads the same meeting and has no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(detailUrl);
  await expect(section.getByRole("list", { name: "Meetings" }).getByRole("listitem")).toHaveCount(1);
  await expect(section.getByRole("button")).toHaveCount(0);
});
