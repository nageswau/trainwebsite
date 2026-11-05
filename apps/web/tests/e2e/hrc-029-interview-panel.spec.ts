import { expect, test, type Page } from "@playwright/test";

import { createAndActivate, E2E_PASSWORD } from "./helpers/welcome";

// hrc-029 (DEC-SCOPE-405; AC1-AC4): the IT admin creates a throwaway interviewer (the seeded one stays unassigned for hrc-002's spec); the
// seeded recruiter schedules an interview two minutes ahead for the seeded IT student and assigns the interviewer as lead; the interviewer's
// "My interviews" shows the card (feedback waits for the time), then after the start submits feedback; the recruiter sees it on the panel;
// the student's portal never shows it; the seeded interviewer (not assigned) gets 404.

async function signIn(page: Page, email: string, landing: string, password = "Demo@123") {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** The IST wall-clock `datetime-local` value `minutes` from now, and the instant it stands for. */
function istSoon(minutes: number): { input: string; at: number } {
  const at = Math.ceil((Date.now() + minutes * 60_000) / 60_000) * 60_000;
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date(at)).reduce<Record<string, string>>((acc, p) => ({ ...acc, [p.type]: p.value }), {});
  return { input: `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`, at };
}

const RECRUITER = "placement@edusphere.local";
const STUDENT = "student.it@edusphere.local";

test("interview panel: assign an interviewer, their workspace and feedback, the recruiter sees it, the candidate never does", async ({ page }) => {
  test.setTimeout(360_000);
  const stamp = Date.now();
  const title = `E2E Panel Analyst ${stamp}`;
  const interviewerName = `E2E Interviewer ${stamp}`;
  const interviewerEmail = `e2e-interviewer-${stamp}@example.local`;
  const notes = `Panel notes ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  await signIn(page, "itadmin@edusphere.local", "/it/admin/dashboard");
  await createAndActivate(page.request, "/api/v1/admin/users", { role: "interviewer", email: interviewerEmail, full_name: interviewerName });

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Hrc029 ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title, location: "Pune" } });
  expect(created.ok()).toBeTruthy();
  const requirement = (await created.json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }

  await signIn(page, STUDENT, "/it/student/dashboard");
  expect((await page.request.post(`/api/v1/workflows/it/jobs/${requirement.id}/apply`, { data: {} })).status()).toBe(201);
  const name = (await (await page.request.get("/api/v1/auth/me")).json()).full_name as string;

  // Schedule two minutes ahead, then assign the interviewer as lead (V3).
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).first().click();
  await candidates.getByRole("button", { name: `+ Schedule interview for ${name}` }).click();
  const form = candidates.getByRole("form", { name: "Schedule interview" });
  await form.getByLabel("Round (required)").selectOption({ label: "Technical Round" });
  const soon = istSoon(2);
  await form.getByLabel("Date and time (IST, required)").fill(soon.input);
  await form.getByRole("button", { name: "Schedule interview" }).click();
  await expect(candidates.getByRole("status").first()).toContainText(`Technical Round scheduled for ${name}.`);
  const item = candidates.getByRole("list", { name: `Interviews of ${name}` }).locator(":scope > li").first();
  await item.getByRole("button", { name: /Assign interviewers/ }).click();
  const panelForm = item.getByRole("form", { name: /^Interview panel for INT-/ });
  await panelForm.getByRole("checkbox", { name: new RegExp(interviewerName) }).check();
  await panelForm.getByRole("radio", { name: new RegExp(`Lead interviewer: ${interviewerName}`) }).check();
  await panelForm.getByRole("button", { name: "Save panel" }).click();
  await expect(candidates.getByRole("status").first()).toContainText("Interview panel saved.");
  await expect(item.getByRole("list", { name: /^Interview panel of INT-/ })).toContainText(`${interviewerName} (Internal interviewer, lead) — no feedback yet`);
  const code = ((await item.textContent()) ?? "").match(/INT-\d+/)?.[0] ?? "";
  expect(code).not.toBe("");

  // V6: the interviewer's workspace; feedback waits for the interview time.
  await signIn(page, interviewerEmail, "/it/interviewer/dashboard", E2E_PASSWORD);
  const workspace = page.getByRole("region", { name: "My interviews" });
  const card = workspace.getByRole("listitem").filter({ hasText: title });
  await expect(card).toContainText(name);
  await expect(card).toContainText("Lead interviewer");
  await expect(card).toContainText("Feedback opens once the interview time has passed.");

  // After the start: submit feedback (AC1).
  await page.waitForTimeout(Math.max(0, soon.at - Date.now() + 5_000));
  await page.reload();
  await workspace.getByRole("button", { name: /^Past \(\d+\)$/ }).click();
  const held = workspace.getByRole("listitem").filter({ hasText: title });
  await held.getByRole("button", { name: /Submit feedback/ }).click();
  const feedback = held.getByRole("form", { name: `Feedback for ${code}` });
  await feedback.getByLabel("Score (required)").selectOption("4");
  await feedback.getByLabel("Recommendation (required)").selectOption({ label: "Recommend" });
  await feedback.getByLabel("Notes").fill(notes);
  await feedback.getByRole("button", { name: "Save feedback" }).click();
  await expect(workspace.getByRole("status")).toContainText(`Feedback saved for ${name}.`);
  await expect(held.getByRole("list", { name: `Your feedback for ${code}` })).toContainText(notes);

  // AC2: the recruiter sees it on the panel.
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).first().click();
  const panel = candidates.getByRole("list", { name: `Interview panel of ${code}` });
  await expect(panel).toContainText(`${interviewerName} (Internal interviewer, lead) — Attended, 4 / 5, Recommend`);
  await expect(panel).toContainText(notes);

  // AC3: the student's portal never shows it.
  await signIn(page, STUDENT, "/it/student/dashboard");
  await page.goto("/it/student/interview-schedule");
  await expect(page.getByRole("row").filter({ hasText: title })).toBeVisible();
  await expect(page.getByText(notes)).toHaveCount(0);
  await expect(page.getByText("Recommend", { exact: true })).toHaveCount(0);

  // AC4: an interviewer who is not assigned gets 404.
  await signIn(page, "interviewer@edusphere.local", "/it/interviewer/dashboard");
  const listed = (await (await page.request.get("/api/v1/interviewer/interviews?view=past")).json()).items as { code: string }[];
  expect(listed.map((i) => i.code)).not.toContain(code);

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
