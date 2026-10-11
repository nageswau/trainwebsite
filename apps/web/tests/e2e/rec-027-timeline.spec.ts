import { expect, test, type Page } from "@playwright/test";

// rec-027 (AC1, AC2; TL1-TL10): the seeded recruiter logs a call on a new company's contact, then adds a follow-up -- the company's Timeline
// shows both, newest first, with actor and summary, without a reload; a candidate call shows on the candidate's Timeline; the seeded
// placement manager reads the company's Timeline.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

function istInput(days: number): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000));
  return `${day}T10:30`;
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("timeline: a call then a follow-up read newest first on the company; a candidate call; the manager reads", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Rec027 ${Date.now()} Technologies`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new?with=contact");
  await page.getByRole("group", { name: "Recruiter contact" }).getByLabel("Contact name (required)").fill("Priya Sharma");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();

  const timeline = page.getByRole("region", { name: "Timeline" });
  await expect(timeline.getByText("No activity yet.")).toBeVisible();

  const calls = page.getByRole("region", { name: "Calls" });
  await calls.getByRole("button", { name: "Log call" }).click();
  const form = calls.getByRole("form", { name: "Log call" });
  await form.getByLabel("Contact (required)").selectOption({ label: "Priya Sharma" });
  await form.getByLabel("Outcome (required)").selectOption("connected");
  await form.getByLabel("Notes").fill("Discussed the Java JD");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(calls.getByText("Call logged.")).toBeVisible();

  const followUps = page.getByRole("region", { name: "Follow-ups" });
  await followUps.getByRole("button", { name: "Add follow-up" }).click();
  const fuForm = followUps.getByRole("form", { name: "Add follow-up" });
  await fuForm.getByLabel("Due date and time (IST, required)").fill(istInput(2));
  await fuForm.getByLabel("Reason (required)").selectOption({ label: "Follow-up for JD" });
  await fuForm.getByRole("button", { name: "Add follow-up" }).click();

  // AC1 + AC2: newest first, each with its actor and summary -- read again after each write, no reload.
  const entries = timeline.getByRole("list", { name: "Company timeline" }).getByRole("listitem");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText("Follow-up added: Follow-up for JD");
  await expect(entries.nth(1)).toContainText("Outgoing call: Connected");
  await expect(entries.nth(1)).toContainText("With Priya Sharma");
  await expect(entries.nth(1)).toContainText("Discussed the Java JD");
  await expect(entries.nth(1)).toContainText("Kiran Placement");

  // A refresh reads the same order (the order is total).
  await page.reload();
  await expect(timeline.getByRole("listitem").nth(0)).toContainText("Follow-up added");

  // The candidate timeline.
  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill("E2E Rec027 Rahul");
  await page.locator("#cand-mobile").fill(`9${String(Date.now()).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateTimeline = page.getByRole("region", { name: "Timeline" });
  await expect(candidateTimeline.getByText("No activity yet.")).toBeVisible();
  const candidateCalls = page.getByRole("region", { name: "Calls" });
  await candidateCalls.getByRole("button", { name: "Log call" }).click();
  const candidateForm = candidateCalls.getByRole("form", { name: "Log call" });
  await candidateForm.getByLabel("Outcome (required)").selectOption("no_answer");
  await candidateForm.getByRole("button", { name: "Save call" }).click();
  await expect(candidateTimeline.getByRole("list", { name: "Candidate timeline" }).getByRole("listitem").first()).toContainText("Outgoing call: No answer");

  // The manager reads the company's timeline.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(detailUrl);
  await expect(page.getByRole("region", { name: "Timeline" }).getByRole("listitem")).toHaveCount(2);
});
