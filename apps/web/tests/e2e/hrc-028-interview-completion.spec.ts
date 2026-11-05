import { expect, test, type Page } from "@playwright/test";

// hrc-028 (DEC-SCOPE-400; AC1-AC4): the seeded recruiter schedules an interview for the seeded IT student with the new fields (round number,
// duration, the candidate's zone Asia/Dubai, platform, instructions), replaces the meeting link (history names it, the old link never shows),
// the student's portal shows only the new link with the time in Dubai, then the recruiter cancels with a reason and the portal reads
// "Cancelled — reason" with no link. The .ics itself is asserted in test_hrc_028_interviews.py (no mailbox in e2e).

async function signIn(page: Page, email: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** An IST wall-clock `datetime-local` value `days` from now at 10:mm (a per-run minute, so reruns never clash on the shared student). */
function istInput(days: number, minute: number): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000));
  return `${day}T10:${String(minute).padStart(2, "0")}`;
}

const RECRUITER = "placement@edusphere.local";
const STUDENT = "student.it@edusphere.local";

test("interview completion: new fields, link replacement, candidate zone, cancel with reason in the portal", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const title = `E2E Interview Analyst ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  await signIn(page, RECRUITER, "/recruiter/dashboard");
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Hrc028 ${stamp} Ltd` } });
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

  // I1 / I2: schedule with the new fields; the item shows the candidate's time in Dubai.
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).first().click();
  await candidates.getByRole("button", { name: `+ Schedule interview for ${name}` }).click();
  const form = candidates.getByRole("form", { name: "Schedule interview" });
  await form.getByLabel("Round (required)").selectOption({ label: "Technical Round" });
  await form.getByLabel("Date and time (IST, required)").fill(istInput(3, stamp % 60));
  await form.getByLabel("Meeting link").fill(`https://meet.example.com/old-${stamp}`);
  await form.getByLabel("Round number").fill("2");
  await form.getByLabel("Duration").selectOption("45");
  await form.getByLabel("Candidate's time zone").selectOption("Asia/Dubai");
  await form.getByLabel("Platform").selectOption({ label: "Google Meet" });
  await form.getByLabel("Instructions").fill("Join 5 minutes early");
  await form.getByRole("button", { name: "Schedule interview" }).click();
  await expect(candidates.getByRole("status").first()).toContainText(`Technical Round scheduled for ${name}.`);
  const item = candidates.getByRole("list", { name: `Interviews of ${name}` }).locator(":scope > li").first();
  await expect(item).toContainText("Technical Round (round 2)");
  await expect(item).toContainText("Candidate's time");
  await expect(item).toContainText("Asia/Dubai (UTC+04:00)");
  await expect(item).toContainText("Google Meet");

  // I4 / AC1: replace the link; the history names it without showing the old one.
  await item.getByRole("button", { name: /^Edit/ }).click();
  const edit = item.getByRole("form", { name: /^Edit interview INT-/ });
  await edit.getByLabel("Meeting link").fill(`https://meet.example.com/new-${stamp}`);
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(candidates.getByRole("status").first()).toContainText("Interview updated. Candidate: notified in the portal.");
  await item.getByText(/^History \(2\)/).click();
  await expect(item).toContainText("Meeting link replaced");
  await expect(item.getByRole("link", { name: /Meeting link/ })).toHaveAttribute("href", `https://meet.example.com/new-${stamp}`);
  await expect(item).not.toContainText(`old-${stamp}`);

  // AC1 / AC4: the student's portal shows only the new link, the time in Dubai.
  await signIn(page, STUDENT, "/it/student/dashboard");
  await page.goto("/it/student/interview-schedule");
  const row = page.getByRole("row").filter({ hasText: title });
  await expect(row).toContainText("Technical Round (round 2)");
  await expect(row).toContainText("Asia/Dubai (UTC+04:00)");
  await expect(row.getByRole("link", { name: `Open meeting link for ${title}` })).toHaveAttribute("href", `https://meet.example.com/new-${stamp}`);
  await expect(page.getByText(`old-${stamp}`)).toHaveCount(0);

  // I3 / AC2: cancel with a required reason; the item and the portal read "Cancelled — reason", no link.
  await signIn(page, RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  await candidates.getByRole("button", { name: `Interviews of ${name}` }).first().click();
  await item.getByRole("button", { name: /^Cancel interview/ }).click();
  const cancel = item.getByRole("form", { name: /^Cancel INT-/ });
  await cancel.getByRole("button", { name: "Cancel interview" }).click();
  await expect(cancel.getByText("Enter the reason")).toBeVisible();
  await cancel.getByLabel("Reason (required, shown to the candidate)").fill("Panel unavailable");
  await cancel.getByRole("button", { name: "Cancel interview" }).click();
  await expect(candidates.getByRole("status").first()).toContainText("Interview cancelled. Candidate: notified in the portal.");
  await expect(item).toContainText("Cancelled — Panel unavailable");
  await expect(item.getByRole("link", { name: /Meeting link/ })).toHaveCount(0);
  await expect(item.getByRole("button")).toHaveCount(0);

  await signIn(page, STUDENT, "/it/student/dashboard");
  await page.goto("/it/student/interview-schedule");
  const cancelled = page.getByRole("row").filter({ hasText: title });
  await expect(cancelled).toContainText("Cancelled — Panel unavailable");
  await expect(cancelled.getByRole("link")).toHaveCount(0);

  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
