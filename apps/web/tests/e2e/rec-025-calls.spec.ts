import { expect, test, type Page } from "@playwright/test";

// rec-025 (AC1-AC3; CA2-CA6): the seeded recruiter logs a call on a new company's contact with a next follow-up -- the contact's Last
// contacted and next follow-up move and the follow-up is listed -- then edits it (same day); a candidate call offers no follow-up; the
// seeded placement manager reads the company's calls without any write control.

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

test("calls: log on a contact with a follow-up, Last contacted, same-day edit; candidate call; the manager reads only", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Rec025 ${Date.now()} Technologies`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new?with=contact");
  await page.getByRole("group", { name: "Recruiter contact" }).getByLabel("Contact name (required)").fill("Priya Sharma");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();

  const contacts = page.getByRole("region", { name: "Contacts" });
  await expect(contacts.getByText("Not yet")).toBeVisible();
  const calls = page.getByRole("region", { name: "Calls" });
  await expect(calls.getByText("No calls logged yet.")).toBeVisible();

  // AC1 + AC2: a connected call with notes and a next follow-up.
  await calls.getByRole("button", { name: "Log call" }).click();
  const form = calls.getByRole("form", { name: "Log call" });
  await form.getByLabel("Contact (required)").selectOption({ label: "Priya Sharma" });
  await form.getByLabel("Outcome (required)").selectOption("connected");
  await form.getByLabel("Minutes").fill("3");
  await form.getByLabel("Notes").fill("Discussed the Java JD");
  await form.getByLabel("Add a next follow-up").check();
  await form.getByLabel("Follow-up due (IST, required)").fill(istInput(2));
  await form.getByLabel("Follow-up reason (required)").selectOption("jd");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(calls.getByText("Call logged. Follow-up added.")).toBeVisible();
  const item = calls.getByRole("listitem").first();
  await expect(item).toContainText("with Priya Sharma");
  await expect(item).toContainText("3 min");
  await expect(contacts.getByText("Not yet")).toHaveCount(0); // AC1
  await expect(page.getByRole("region", { name: "Follow-ups" }).getByText("Follow-up for JD")).toBeVisible(); // AC2

  // AC3: today's call can be edited (the outcome is locked).
  await item.getByRole("button", { name: /Edit/ }).click();
  const edit = item.getByRole("form", { name: "Edit call" });
  await expect(edit.getByLabel("Outcome (required)")).toHaveCount(0);
  await edit.getByLabel("Notes").fill("Discussed the Java JD and fees");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(calls.getByText("Call updated.")).toBeVisible();
  await expect(calls.getByRole("listitem").first()).toContainText("and fees");

  // A candidate call: no contact, no follow-up.
  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill("E2E Rahul Sharma");
  await page.locator("#cand-mobile").fill(`9${String(Date.now()).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateCalls = page.getByRole("region", { name: "Calls" });
  await candidateCalls.getByRole("button", { name: "Log call" }).click();
  const candidateForm = candidateCalls.getByRole("form", { name: "Log call" });
  await expect(candidateForm.getByLabel("Add a next follow-up")).toHaveCount(0);
  await candidateForm.getByLabel("Outcome (required)").selectOption("no_answer");
  await candidateForm.getByRole("button", { name: "Save call" }).click();
  await expect(candidateCalls.getByText("Call logged.")).toBeVisible();
  await expect(candidateCalls.getByRole("listitem").first()).toContainText("Not connected");

  // The manager reads the company's calls; no Log call, no Edit.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(detailUrl);
  const managerCalls = page.getByRole("region", { name: "Calls" });
  await expect(managerCalls.getByRole("listitem")).toHaveCount(1);
  await expect(managerCalls.getByRole("button", { name: "Log call" })).toHaveCount(0);
  await expect(managerCalls.getByRole("button", { name: /Edit/ })).toHaveCount(0);
});
