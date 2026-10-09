import { expect, test, type Page } from "@playwright/test";

// rec-020 (AC1; IV3-IV5, IV10, IV12): the seeded recruiter schedules an HR round for a candidate on a requirement (the application moves to
// Interview), a clash at the same time is refused, a reschedule keeps the old -> new history, the interview is confirmed and sits under
// Upcoming; the seeded placement manager reads it without any write control. AC2 (No Show / Completed only after the time) needs a past
// interview, which the API refuses to create, so it is covered by test_rec_020_interviews.py and the component tests.

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

test("interviews: schedule an HR round, clash refused, reschedule history, confirm, Upcoming; the manager reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const name = `E2E Interviewee ${stamp}`;
  const consoleErrors: string[] = [];
  // The clash step is refused on purpose: the browser logs that 409 itself, which is not a page error.
  page.on("console", (message) => message.type() === "error" && !message.text().includes("status of 409") && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/recruiter/") && response.status() >= 500 && failedCalls.push(response.url()));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec020 ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `Java Developer ${stamp}`, location: "Pune" } });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;

  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(`9${String(stamp).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateId = page.url().split("/").at(-1)?.split("?")[0];
  expect((await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId, status: "shortlisted" } })).status()).toBe(201);

  // IV5: schedule an HR round from the candidate's row; the application moves to Interview.
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).click();
  await expect(candidates.getByText("No interviews yet.")).toBeVisible();
  await candidates.getByRole("button", { name: `+ Schedule interview for ${name}` }).click();
  const form = candidates.getByRole("form", { name: "Schedule interview" });
  await form.getByLabel("Round (required)").selectOption({ label: "HR Round" });
  await form.getByLabel("Date and time (IST, required)").fill(istInput(2));
  await form.getByLabel("Meeting link").fill("https://meet.example.com/rec020");
  await form.getByLabel("Interviewer").fill("Meera (HR)");
  await form.getByRole("button", { name: "Schedule interview" }).click();
  await expect(candidates.getByRole("status").first()).toContainText(`HR Round scheduled for ${name}.`);
  const row = candidates.getByRole("list", { name: "Candidates on this requirement" }).getByRole("listitem").first();
  await expect(row.locator(".badge").first()).toHaveText("Interview");
  const interviews = candidates.getByRole("list", { name: `Interviews of ${name}` });
  const item = interviews.locator(":scope > li").first();
  await expect(item).toContainText("HR Round");
  await expect(item).toContainText("Scheduled");
  await expect(item.getByRole("link", { name: /Meeting link/ })).toHaveAttribute("href", "https://meet.example.com/rec020");

  // IV6: the same candidate at the same time is refused, in the server's words.
  await candidates.getByRole("button", { name: `+ Schedule interview for ${name}` }).click();
  const second = candidates.getByRole("form", { name: "Schedule interview" });
  await second.getByLabel("Round (required)").selectOption({ label: "Technical Round" });
  await second.getByLabel("Date and time (IST, required)").fill(istInput(2));
  await second.getByRole("button", { name: "Schedule interview" }).click();
  await expect(second.getByRole("alert")).toContainText("already has an interview scheduled at this time");
  await second.getByRole("button", { name: "Cancel" }).click();

  // AC1: rescheduling keeps the old -> new history.
  await item.getByRole("button", { name: /^Reschedule/ }).click();
  const move = item.getByRole("form", { name: /^Reschedule INT-/ });
  await move.getByLabel("New date and time (IST, required)").fill(istInput(4));
  await move.getByLabel("Reason").fill("Panel unavailable");
  await move.getByRole("button", { name: "Reschedule" }).click();
  await expect(candidates.getByRole("status").first()).toContainText("Interview rescheduled.");
  await expect(item).toContainText("Rescheduled");
  await item.getByText(/^History \(2\)/).click();
  await expect(item).toContainText(/Rescheduled from .* to .*Panel unavailable/);

  // IV3: confirm it (No Show / Completed are not offered before the time).
  await item.getByRole("button", { name: /^Change status/ }).click();
  const status = item.getByRole("form", { name: /^Change status of INT-/ });
  await expect(status.getByLabel("New status (required)").locator("option")).toHaveText(["Choose a status", "Confirmed", "On Hold"]);
  await status.getByLabel("New status (required)").selectOption({ label: "Confirmed" });
  await status.getByRole("button", { name: "Save status" }).click();
  await expect(item).toContainText("Confirmed");

  // IV12: it sits under Upcoming, under its IST day.
  await page.goto("/recruiter/interviews");
  await expect(page.getByRole("button", { name: /^Upcoming/ })).toHaveAttribute("aria-current", "page");
  const card = page.locator("li").filter({ hasText: name });
  await expect(card).toHaveCount(1);
  await expect(card.getByRole("link", { name })).toHaveAttribute("href", `/recruiter/requirements/${requirementId}`);
  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);

  // IV10: the manager reads the same interview with no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto("/recruiter/interviews");
  const read = page.locator("li").filter({ hasText: name });
  await expect(read).toHaveCount(1);
  await expect(read.getByRole("button")).toHaveCount(0);
});
