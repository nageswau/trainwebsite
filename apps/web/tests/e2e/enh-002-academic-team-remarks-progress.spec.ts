import { test, expect, type Locator, type Page } from "@playwright/test";

// ENH-002 -- Academic Team: `teacher_remarks` on a result, the portfolio progress summary,
// and DEC-ROLE-007's actor separation. Requires the stack running via `docker compose up`
// with `python -m app.seed` applied (seeds overseasadmin@edusphere.local/Demo@123). Builds its
// own throwaway School + Coordinator + Academic Team + Career Counselor + students per run,
// like the SCH-00x specs.

const DEFAULT_PASSWORD = "ChangeMe@12345";
const PARENT_PASSWORD = "Sup3r-Secret-Pass!";

type Staff = { role: string; name: string; email: string };

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function provisionSchool(page: Page, schoolName: string, coordinatorEmail: string, staff: Staff[]) {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "ENH-002 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.click('button:has-text("Create school + seed Coordinator")');
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.goto("/overseas/admin/school-staff");
  for (const member of staff) {
    await page.selectOption("#staff-role", member.role);
    await page.fill("#staff-name", member.name);
    await page.fill("#staff-email", member.email);
    await page.selectOption("#staff-schools", { label: schoolName });
    await page.click('button:has-text("Create account")');
    await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });
  }
}

async function addStudent(page: Page, data: Record<string, string>) {
  const response = await page.request.post("/api/v1/school/students", { data });
  expect(response.status()).toBe(201);
  return (await response.json()) as { id: string; development_invite_token?: string };
}

async function fillResult(page: Page, schoolName: string, f: { student: string; subject: string; obtained: string; remarks: string }) {
  await page.selectOption("#result-student", { label: `${f.student} — ${schoolName}` });
  await page.fill("#result-year", "2026");
  await page.fill("#result-term", "Term 1");
  await page.fill("#result-subject", f.subject);
  await page.fill("#result-max", "100");
  await page.fill("#result-obtained", f.obtained);
  await page.fill("#result-remarks", f.remarks);
}

function card(page: Page, heading: string | RegExp): Locator {
  return page.locator(".card", { has: page.getByRole("heading", { name: heading, exact: typeof heading === "string" }) });
}

test("academic team records remarks and sees portfolio progress; a different member publishes; the parent sees the remark (ENH-002)", async ({ page }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const schoolName = `E2E ENH-002 School ${unique}`;
  const coordinatorEmail = `enh002-e2e-coord-${unique}@example.local`;
  const uploaderEmail = `enh002-e2e-academic1-${unique}@example.local`;
  const verifierEmail = `enh002-e2e-academic2-${unique}@example.local`;
  const counselorEmail = `enh002-e2e-counselor-${unique}@example.local`;
  const parentEmail = `enh002-e2e-parent-${unique}@example.local`;
  const remark = `Strong algebra, ${unique}`;
  const draftRemark = `DRAFT-ONLY ${unique}`;

  await provisionSchool(page, schoolName, coordinatorEmail, [
    { role: "academic_team", name: "ENH2 Uploader", email: uploaderEmail },
    { role: "academic_team", name: "ENH2 Verifier", email: verifierEmail },
    { role: "career_counselor", name: "ENH2 Counselor", email: counselorEmail },
  ]);

  await signIn(page, coordinatorEmail, DEFAULT_PASSWORD, "**/school/coordinator/dashboard");
  const alice = await addStudent(page, { full_name: "ENH2 Alice", grade_or_class: "Grade 8", parent_name: "ENH2 Parent", parent_email: parentEmail });
  await addStudent(page, { full_name: "ENH2 Bob", grade_or_class: "Grade 8" });
  expect(alice.development_invite_token).toBeTruthy();

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${alice.development_invite_token}/accept`);
  await page.fill("#invite-password", PARENT_PASSWORD);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");

  // Uploader: progress starts empty, then a result with remarks lands as a Draft.
  await signIn(page, uploaderEmail, DEFAULT_PASSWORD, "**/school/academic-team/dashboard");
  const progress = card(page, "Portfolio progress");
  await expect(progress.getByRole("row", { name: /ENH2 Alice/ })).toContainText("No results yet");
  await expect(progress.getByRole("row", { name: /ENH2 Bob/ })).toContainText("No results yet");

  await fillResult(page, schoolName, { student: "ENH2 Alice", subject: "Mathematics", obtained: "80", remarks: remark });
  await page.click('button:has-text("Save as Draft")');
  await expect(page.getByText("Mathematics result saved as Draft.")).toBeVisible();
  await fillResult(page, schoolName, { student: "ENH2 Alice", subject: "Physics", obtained: "60", remarks: draftRemark });
  await page.click('button:has-text("Save as Draft")');
  await expect(page.getByText("Physics result saved as Draft.")).toBeVisible();

  const results = card(page, "Results");
  const mathRow = results.getByRole("row", { name: /Mathematics/ });
  await expect(mathRow).toContainText(remark);
  await expect(mathRow).toContainText("Ask another Academic Team member to verify");
  await expect(mathRow.getByRole("button", { name: "Verify" })).toHaveCount(0);
  // Progress is the mean of each result's own percentage: (80 + 60) / 2.
  await expect(progress.getByRole("row", { name: /ENH2 Alice/ })).toContainText("70%");
  await expect(progress.getByRole("row", { name: /ENH2 Alice/ })).toContainText("2");
  await expect(progress.getByRole("row", { name: /ENH2 Bob/ })).toContainText("No results yet");

  const listed = (await (await page.request.get("/api/v1/school/academic-team/results")).json()) as { id: string; subject: string }[];
  const mathId = listed.find((r) => r.subject === "Mathematics")?.id;
  expect(mathId).toBeTruthy();

  // A different member: cannot rewrite the uploader's draft, can verify and publish it.
  await signIn(page, verifierEmail, DEFAULT_PASSWORD, "**/school/academic-team/dashboard");
  const hijack = await page.request.patch(`/api/v1/school/academic-team/results/${mathId}`, { data: { marks_obtained: 99 } });
  expect(hijack.status()).toBe(403);
  await card(page, "Results").getByRole("row", { name: /Mathematics/ }).getByRole("button", { name: "Verify" }).click();
  await expect(page.getByText("Result verified.")).toBeVisible();
  await card(page, "Results").getByRole("row", { name: /Mathematics/ }).getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Result published.")).toBeVisible();

  // A sibling internal role is not an Academic Team member.
  await signIn(page, counselorEmail, DEFAULT_PASSWORD, "**/school/career-counselor/dashboard");
  expect((await page.request.get("/api/v1/school/academic-team/progress")).status()).toBe(403);

  // Parent: the published result's remark is shown; the still-draft result is not.
  await signIn(page, parentEmail, PARENT_PASSWORD, "**/school/parent/dashboard");
  await page.goto(`/school/parent/children/${alice.id}`);
  const academic = card(page, "Academic results");
  await expect(academic.getByRole("columnheader", { name: "Remarks" })).toBeVisible();
  await expect(academic.getByRole("row", { name: /Mathematics/ })).toContainText(remark);
  await expect(academic.getByText("Physics")).toHaveCount(0);
  await expect(page.getByText(draftRemark)).toHaveCount(0);
});

test("a network failure while saving or verifying shows an error and recovers instead of freezing the form (ENH-002)", async ({ page, context }) => {
  test.setTimeout(150_000);
  const unique = Date.now();
  const schoolName = `E2E ENH-002 Offline School ${unique}`;
  const coordinatorEmail = `enh002-e2e-off-coord-${unique}@example.local`;
  const uploaderEmail = `enh002-e2e-off-academic1-${unique}@example.local`;
  const verifierEmail = `enh002-e2e-off-academic2-${unique}@example.local`;
  const remark = `Typed before the outage ${unique}`;

  await provisionSchool(page, schoolName, coordinatorEmail, [
    { role: "academic_team", name: "ENH2 Offline Uploader", email: uploaderEmail },
    { role: "academic_team", name: "ENH2 Offline Verifier", email: verifierEmail },
  ]);
  await signIn(page, coordinatorEmail, DEFAULT_PASSWORD, "**/school/coordinator/dashboard");
  await addStudent(page, { full_name: "ENH2 Offline Student", grade_or_class: "Grade 8" });

  // Save while offline: an error appears, the button comes back, typed input is kept.
  await signIn(page, uploaderEmail, DEFAULT_PASSWORD, "**/school/academic-team/dashboard");
  await fillResult(page, schoolName, { student: "ENH2 Offline Student", subject: "Mathematics", obtained: "75", remarks: remark });
  await context.setOffline(true);
  await page.click('button:has-text("Save as Draft")');
  await expect(page.getByText(/could not reach the server/i)).toBeVisible();
  const save = page.getByRole("button", { name: "Save as Draft" });
  await expect(save).toBeEnabled();
  await expect(page.locator("#result-remarks")).toHaveValue(remark);

  // Back online, the same form submits without a reload.
  await context.setOffline(false);
  await save.click();
  await expect(page.getByText("Mathematics result saved as Draft.")).toBeVisible();

  // Verify while offline: same recovery, then it works online.
  await signIn(page, verifierEmail, DEFAULT_PASSWORD, "**/school/academic-team/dashboard");
  const verify = card(page, "Results").getByRole("row", { name: /Mathematics/ }).getByRole("button", { name: "Verify" });
  await context.setOffline(true);
  await verify.click();
  await expect(page.getByText(/could not reach the server/i)).toBeVisible();
  await expect(verify).toBeEnabled();
  await context.setOffline(false);
  await verify.click();
  await expect(page.getByText("Result verified.")).toBeVisible();
});
