import { expect, test, type Page } from "@playwright/test";

// rec-021 (AC1, AC2; FB2-FB5): the seeded recruiter schedules an HR round, which offers no feedback until it is Completed. The interview is
// moved into the past through the legacy staff PATCH (rec-020 IV11: a past time is a reschedule there; the recruiter API refuses one),
// marked Completed, and the feedback is recorded: a rating out of range is impossible in the form, Overall is required, the decision
// Selected sets the status and the suggested Manager Round opens as a pre-chosen schedule draft. The manager then reads the feedback
// without any write control.

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

test("interview feedback: only after Completed, overall required, decision sets the status, next round draft; the manager reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const name = `E2E Feedback ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/recruiter/") && response.status() >= 500 && failedCalls.push(response.url()));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec021 ${stamp} Ltd` } });
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
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId, status: "shortlisted" } });
  expect(added.status()).toBe(201);
  const applicationId = (await added.json()).application.id as string;
  const scheduled = await page.request.post("/api/v1/recruiter/interviews", {
    data: { application_id: applicationId, round: "hr_round", scheduled_at: `${istInput(2)}:00+05:30`, mode: "Online", notify: false },
  });
  expect(scheduled.status()).toBe(201);
  const interview = (await scheduled.json()).interview as { id: string; code: string };

  // AC1: a Scheduled interview offers no feedback.
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).click();
  const item = candidates.getByRole("list", { name: `Interviews of ${name}` }).locator(":scope > li").first();
  await expect(item).toContainText("Scheduled");
  await expect(item.getByRole("button", { name: /feedback/i })).toHaveCount(0);

  // Into the past through the legacy staff route, then Completed in the UI.
  const past = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  expect((await page.request.patch(`/api/v1/workflows/it/interviews/${interview.id}`, { data: { scheduled_at: past } })).ok()).toBeTruthy();
  await page.reload();
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).click();
  await item.getByRole("button", { name: /^Change status/ }).click();
  const status = item.getByRole("form", { name: /^Change status of INT-/ });
  await status.getByLabel("New status (required)").selectOption({ label: "Completed" });
  await status.getByRole("button", { name: "Save status" }).click();
  await expect(item.locator(".badge")).toHaveText("Completed");

  // FB3: Overall is required; then the whole form saves, the decision sets the status and AC2's draft opens.
  await item.getByRole("button", { name: `Record feedback for ${interview.code}` }).click();
  const form = item.getByRole("form", { name: `Feedback for ${interview.code}` });
  await form.getByRole("button", { name: "Save feedback" }).click();
  await expect(form.getByText("Choose an overall rating")).toBeVisible();
  await form.getByLabel("Technical rating").selectOption("5");
  await form.getByLabel("Communication rating").selectOption("3");
  await form.getByLabel("Overall rating (required)").selectOption("4");
  await form.getByLabel("Strengths").fill("Strong Java fundamentals");
  await form.getByLabel("Company feedback").fill("Client liked the problem solving");
  await form.getByLabel("Final decision").selectOption({ label: "Selected" });
  await form.getByLabel("Next round").selectOption({ label: "Manager Round" });
  await form.getByRole("button", { name: "Save feedback" }).click();
  await expect(candidates.getByRole("status").first()).toContainText("Feedback saved. Next round suggested: Manager Round.");
  await expect(item.locator(".badge")).toHaveText("Selected");
  const summary = item.getByRole("list", { name: `Feedback of ${interview.code}` });
  await expect(summary).toContainText("Overall: 4 / 5");
  await expect(summary).toContainText("Next round: Manager Round");
  const draft = candidates.getByRole("form", { name: "Schedule interview" });
  await expect(draft.getByLabel("Round (required)")).toHaveValue("manager_round");
  await draft.getByRole("button", { name: "Cancel" }).click();
  await expect(candidates.getByRole("button", { name: `+ Schedule Manager Round (suggested) for ${name}` })).toBeVisible();

  // FB1: a decided interview keeps its decision; its text is still editable.
  await item.getByRole("button", { name: `Edit feedback for ${interview.code}` }).click();
  const edit = item.getByRole("form", { name: `Feedback for ${interview.code}` });
  await expect(edit.getByLabel("Overall rating (required)")).toHaveValue("4");
  await edit.getByLabel("Final decision").selectOption({ label: "Rejected" });
  await expect(edit.getByLabel("Next round")).toBeDisabled();
  await edit.getByRole("button", { name: "Save feedback" }).click();
  await expect(edit.locator(".form-error[role=alert], [role=alert] .form-error").first()).toContainText("cannot move from Selected to Rejected");
  expect(consoleErrors.filter((t) => !t.includes("status of 409"))).toEqual([]);
  expect(failedCalls).toEqual([]);

  // FB8: the manager reads the feedback with no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto("/recruiter/interviews?view=closed");
  const read = page.locator("li").filter({ hasText: name });
  await expect(read).toHaveCount(1);
  await expect(read.getByRole("list", { name: `Feedback of ${interview.code}` })).toContainText("Strengths: Strong Java fundamentals");
  await expect(read.getByRole("button")).toHaveCount(0);
});
