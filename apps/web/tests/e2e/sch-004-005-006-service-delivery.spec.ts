import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-004/005/006 -- Career Guidance, Psychometric Assessment, Academic Results.
// Requires the stack running via `docker compose up` with `python -m app.seed` already
// applied (seeds an `overseas_admin` account, overseasadmin@edusphere.local/Demo@123).
// Registers its own throwaway School + Coordinator + specialized staff + student per run.
//
// Covers DEC-SCOPE-014 (only Overseas Admin provisions Academic Team/Career Counselor/
// Psychometric Team accounts, with a per-school portfolio) and DEC-ROLE-007 (a different
// Academic Team member must verify/publish a result than the one who uploaded it).

test("overseas admin provisions specialized staff, they deliver services, and school-side roles see a read-only summary (SCH-004/005/006)", async ({ page }) => {
  // The shared dev DB accumulates schools/staff across every prior test run with no
  // cleanup (RAID.md I-06) -- the Admin's School portfolio dropdown has grown to
  // hundreds of entries, which slows each render enough to need generous timeouts here.
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `sch456-e2e-coord-${unique}@example.local`;
  const schoolName = `E2E Service School ${unique}`;
  const uploaderEmail = `sch456-e2e-academic1-${unique}@example.local`;
  const verifierEmail = `sch456-e2e-academic2-${unique}@example.local`;
  const counselorEmail = `sch456-e2e-counselor-${unique}@example.local`;
  const psychEmail = `sch456-e2e-psych-${unique}@example.local`;

  // 1. Overseas Admin creates the school + seed Coordinator.
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E SVC Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  // 2. Overseas Admin provisions two Academic Team accounts (uploader + verifier/
  // publisher, per DEC-ROLE-007), one Career Counselor, one Psychometric Team member --
  // each with the new school in their portfolio.
  await page.goto("/overseas/admin/school-staff");
  await expect(page.getByText(schoolName)).toBeVisible();

  async function createStaff(role: string, name: string, email: string) {
    await page.selectOption("#staff-role", role);
    await page.fill("#staff-name", name);
    await page.fill("#staff-email", email);
    await page.selectOption("#staff-schools", { label: schoolName });
    await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");
    await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });
  }

  await createStaff("academic_team", "E2E Academic Uploader", uploaderEmail);
  await createStaff("academic_team", "E2E Academic Verifier", verifierEmail);
  await createStaff("career_counselor", "E2E Career Counselor", counselorEmail);
  await createStaff("psychometric_team", "E2E Psychometric Team", psychEmail);

  await expect(page.getByRole("cell", { name: uploaderEmail })).toBeVisible();
  await expect(page.getByRole("cell", { name: verifierEmail })).toBeVisible();

  // 3. Coordinator adds a student to the roster.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "E2E Service Student");
  await page.click('button:has-text("Add student")');
  await expect(page.getByRole("cell", { name: "E2E Service Student" })).toBeVisible();

  // 4. Academic Team uploader creates a Draft result, sees no working Verify action on it.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", uploaderEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");

  // Scoped to this specific select -- SCH-009 added its own Test Prep/Language student
  // pickers to the same Academic Team dashboard, so an unscoped option lookup now matches
  // this same option label across all three selects.
  await expect(page.locator("#result-student").getByRole("option", { name: /E2E Service Student/ })).toHaveCount(1);
  await page.selectOption("#result-student", { label: `E2E Service Student — ${schoolName}` });
  await page.fill("#result-year", "2026");
  await page.fill("#result-term", "Term 1");
  await page.fill("#result-subject", "Mathematics");
  await page.fill("#result-max", "100");
  await page.fill("#result-obtained", "82");
  await page.click('button:has-text("Save as Draft")');
  await expect(page.getByText(/Mathematics result saved as Draft\./)).toBeVisible();
  await expect(page.getByText(/Ask another Academic Team member to verify/)).toBeVisible();

  // 5. A different Academic Team member (the verifier) verifies then publishes it.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", verifierEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");

  const resultRow = page.locator("tr", { hasText: "Mathematics" });
  await resultRow.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByText(/Result verified\./)).toBeVisible();
  await resultRow.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText(/Result published\./)).toBeVisible();
  await expect(resultRow.getByText("published")).toBeVisible();

  // 6. Career Counselor adds a guidance record for the same portfolio student.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", counselorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/career-counselor/dashboard");

  await page.selectOption("#career-student", { label: `E2E Service Student — ${schoolName}` });
  await page.selectOption("#career-type", "guidance_session");
  await page.fill("#career-notes", "Discussed engineering vs. commerce streams.");
  await page.click('button:has-text("Save record")');
  await expect(page.getByText(/Record saved\./)).toBeVisible();
  await expect(page.getByRole("cell", { name: "Guidance session" })).toBeVisible();

  // 7. Psychometric Team assigns an assessment and attaches a report.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", psychEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/psychometric-team/dashboard");

  await page.selectOption("#psych-student", { label: `E2E Service Student — ${schoolName}` });
  await page.fill("#psych-type", "Aptitude Test");
  await page.click('button:has-text("Assign assessment")');
  await expect(page.getByText(/Assessment assigned\./)).toBeVisible();

  await page.click('button:has-text("Attach report")');
  const attachCard = page.locator(".action-card", { hasText: "Attach report" });
  await attachCard.locator("#report-url").fill("/local-files/uploads/e2e-report.pdf");
  await attachCard.getByRole("button", { name: "Attach", exact: true }).click();
  await expect(page.getByText(/Report attached\./)).toBeVisible();

  // 8. The Coordinator's dashboard now shows a read-only summary reflecting all three --
  // the published result (a Draft/Verified one never counts here), the career record, and
  // the psychometric assessment.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await expect(page.getByText("Results & guidance")).toBeVisible();
  await expect(page.getByText(/1 published result, 1 career guidance\/counselling record, 1 psychometric assessment\./)).toBeVisible();
});

test("a newly provisioned specialized staff account with an empty portfolio can't act on any student yet (SCH-004/005/006 provisioning)", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const emptyPortfolioEmail = `sch456-e2e-empty-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "career_counselor");
  await page.fill("#staff-name", "E2E Empty Portfolio Counselor");
  await page.fill("#staff-email", emptyPortfolioEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");
  await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", emptyPortfolioEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/career-counselor/dashboard");

  await expect(page.getByText(/No students in your portfolio yet/)).toBeVisible();
});

test("the School portfolio search narrows the dropdown without losing a selection made before searching", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const alphaName = `E2E Search Alpha School ${unique}`;
  const betaName = `E2E Search Beta School ${unique}`;
  const staffEmail = `sch456-e2e-search-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  for (const name of [alphaName, betaName]) {
    await page.goto("/overseas/admin/schools");
    await page.fill("#school-name", name);
    await page.fill("#school-coordinator-name", "E2E Search Coordinator");
    await page.fill("#school-coordinator-email", `sch456-e2e-search-coord-${unique}-${name === alphaName ? "a" : "b"}@example.local`);
    await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
    await expect(page.getByText(/School created\./)).toBeVisible();
  }

  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "academic_team");
  await page.fill("#staff-name", "E2E Search Staff");
  await page.fill("#staff-email", staffEmail);

  // Search narrows the list to Alpha only, select it.
  await page.fill('input[placeholder="Search schools…"]', "Search Alpha");
  await expect(page.locator("#staff-schools option")).toHaveCount(1);
  await page.selectOption("#staff-schools", { label: alphaName });
  await expect(page.getByText("(1 selected)")).toBeVisible();

  // Clearing the search brings Beta back into view -- Alpha's selection (now hidden
  // during the search above) must not have been silently dropped.
  await page.fill('input[placeholder="Search schools…"]', "");
  await expect(page.getByText("(1 selected)")).toBeVisible();

  // Search again and add Beta -- both selections must now be counted.
  await page.fill('input[placeholder="Search schools…"]', "Search Beta");
  await page.selectOption("#staff-schools", { label: betaName });
  await expect(page.getByText("(2 selected)")).toBeVisible();

  await createAndActivateFromUi(page, 'button:has-text("Create account")', "/overseas-admin/school-staff");
  await expect(page.getByText(/Account created for/)).toBeVisible({ timeout: 20_000 });

  const staffList = await (await page.request.get("/api/v1/overseas-admin/school-staff")).json();
  const created = staffList.find((s: { email: string }) => s.email === staffEmail);
  expect(created).toBeTruthy();
  expect(created.school_ids).toHaveLength(2);
});

test("Select all / Select visible / Clear visible / Clear all act on the School portfolio picker as expected", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const alphaName = `E2E Bulk Alpha School ${unique}`;
  const betaName = `E2E Bulk Beta School ${unique}`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  for (const name of [alphaName, betaName]) {
    await page.goto("/overseas/admin/schools");
    await page.fill("#school-name", name);
    await page.fill("#school-coordinator-name", "E2E Bulk Coordinator");
    await page.fill("#school-coordinator-email", `sch456-e2e-bulk-coord-${unique}-${name === alphaName ? "a" : "b"}@example.local`);
    await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
    await expect(page.getByText(/School created\./)).toBeVisible();
  }

  await page.goto("/overseas/admin/school-staff");
  const selectAllButton = page.getByRole("button", { name: /^Select all \(\d+\)$/ });
  const totalCount = Number((await selectAllButton.textContent())?.match(/\((\d+)\)/)?.[1]);
  expect(totalCount).toBeGreaterThan(2);

  // Select all -> every school, including ones never touched by search.
  await selectAllButton.click();
  await expect(page.getByText(`(${totalCount} selected)`)).toBeVisible();

  // Clear all -> back to nothing selected (no "(N selected)" badge at all).
  await page.getByRole("button", { name: "Clear all" }).click();
  await expect(page.getByText(/\(\d+ selected\)/)).toHaveCount(0);

  // Select visible, scoped to a search, only adds the currently-filtered schools.
  await page.fill('input[placeholder="Search schools…"]', "Bulk Alpha");
  await page.getByRole("button", { name: /^Select visible/ }).click();
  await expect(page.getByText("(1 selected)")).toBeVisible();

  // Selecting visible again under a *different* search adds to the existing selection,
  // it does not replace it.
  await page.fill('input[placeholder="Search schools…"]', "Bulk Beta");
  await page.getByRole("button", { name: /^Select visible/ }).click();
  await expect(page.getByText("(2 selected)")).toBeVisible();

  // Clear visible only removes what's currently filtered (Beta) -- Alpha's selection,
  // hidden right now by the same search, must survive.
  await page.getByRole("button", { name: "Clear visible" }).click();
  await expect(page.getByText("(1 selected)")).toBeVisible();

  // Clearing the search brings Alpha back into view -- its selection must still hold.
  await page.fill('input[placeholder="Search schools…"]', "");
  await expect(page.getByText("(1 selected)")).toBeVisible();
});
