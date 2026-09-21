import { test, expect, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-005 -- student school transfer. Requires the stack running via `docker compose up` with `python -m app.seed` applied (seeds
// overseasadmin@edusphere.local/Demo@123). Builds two throwaway schools; the students, coordinators and parent are unique to this run, so it
// leaves no shared state behind (nothing here is global except the admin's queue, which is only ever read for this run's own row).

const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";
const PARENT_PASSWORD = "Sup3r-Secret-Pass!";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function createSchool(page: Page, unique: number, tag: string) {
  const coordinatorEmail = `enh005-e2e-${tag}-${unique}@example.local`;
  const name = `E2E ENH-005 School ${tag} ${unique}`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", name);
  await page.fill("#school-coordinator-name", `E2E ENH-005 Coordinator ${tag}`);
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  return { coordinatorEmail, name };
}

async function createStudent(page: Page, data: Record<string, unknown>) {
  const response = await page.request.post("/api/v1/school/students", { data });
  expect(response.status()).toBe(201);
  return response.json();
}

const row = (page: Page, text: string) => page.getByRole("listitem").filter({ hasText: text });

test("a coordinator requests a transfer, an admin approves it by keyboard, and both schools and the parent see the result (ENH-005)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const a = await createSchool(page, unique, "a");
  const b = await createSchool(page, unique, "b");
  // A school whose name is one very long word. The destination <select> sizes itself to its longest option, and once pushed the student page
  // to 2,600px wide; jsdom cannot measure layout, so this is the guard (found by the second browser QA pass).
  const longSchool = await page.request.post("/api/v1/overseas-admin/schools", { data: { name: "N".repeat(200), coordinator_full_name: "E2E Long Name Coordinator", coordinator_email: `enh005-e2e-long-${unique}@example.local` } });
  expect(longSchool.status()).toBe(201);

  // School A: one student who will transfer (with a parent), and one that School B will ask for by Student ID.
  await signIn(page, a.coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const kidName = `E2E Transfer Kid ${unique}`;
  const parentEmail = `enh005-e2e-parent-${unique}@example.local`;
  const kid = await createStudent(page, { full_name: kidName, grade_or_class: "Grade 8-A", grade_level: 8, parent_name: "E2E Transfer Parent", parent_email: parentEmail });
  const other = await createStudent(page, { full_name: `E2E Transfer Other ${unique}`, grade_or_class: "Grade 7-A", grade_level: 7 });
  expect(kid.development_invite_token).toBeTruthy();

  // The parent accepts their invite BEFORE the transfer. (A parent still holding an unaccepted invite when the student transfers ends up with
  // no child linked: approval clears `pending_parent_email`, and `accept_invite` only links students at the invite's own school. That gap is
  // recorded in DEC-SCOPE-021 as a limit awaiting a decision, so it is deliberately not exercised as if it worked.)
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${kid.development_invite_token}/accept`);
  await page.fill("#invite-password", PARENT_PASSWORD);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await signIn(page, a.coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");

  // Outgoing: the request lives in a disclosure on the student's page, and is reversible, so there is no confirm step.
  await page.goto(`/school/coordinator/students/${kid.id}`);
  await page.getByText("Request a transfer").click();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: "the student page overflows horizontally with the transfer form open and a very long school name in the list" }).toBe(true);
  await page.selectOption("#transfer-destination", { label: b.name });
  await page.fill("#transfer-reason", "Family is moving");
  await page.getByRole("button", { name: "Request transfer" }).click();
  await expect(page.getByText(/Transfer request sent for review/)).toBeVisible();
  await page.goto("/school/coordinator/transfers");
  await expect(row(page, kidName)).toContainText("Pending review");
  await expect(row(page, kidName)).toContainText(b.name);

  // Incoming (School B asks for School A's other student by code): the same neutral message for any code, and the row is redacted.
  await signIn(page, b.coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  await page.goto("/school/coordinator/transfers");
  await page.fill("#incoming-code", "00000000"); // nobody has this code
  await page.getByRole("button", { name: "Request student" }).click();
  const neutral = "If that Student ID belongs to a student at another school, your request has been sent to an admin for review.";
  await expect(page.getByText(neutral)).toBeVisible();
  await page.fill("#incoming-code", other.student_code); // a real student at another school
  await page.getByRole("button", { name: "Request student" }).click();
  await expect(page.getByText(neutral)).toBeVisible();
  await expect(row(page, `Student ID ${other.student_code}`)).toContainText("Student details are shown once approved");
  await expect(page.getByText(`E2E Transfer Other ${unique}`)).toHaveCount(0); // never disclosed before approval

  // Admin: the queue shows the request, and approve is two-step. Keyboard only: Enter opens the confirm with focus on it, Escape returns focus.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/school-transfers");
  const queueRow = row(page, kidName);
  await expect(queueRow).toContainText("Family is moving");
  const approve = page.getByRole("button", { name: `Approve transfer of ${kidName} to ${b.name}` });
  await approve.focus();
  await approve.press("Enter");
  await expect(page.getByRole("button", { name: "Confirm approval" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(approve).toBeFocused();
  await approve.press("Enter");
  await page.getByRole("button", { name: "Confirm approval" }).press("Enter");
  await expect(page.getByText(new RegExp(`Moved ${kidName} to ${b.name}\\.`))).toBeVisible();
  await expect(row(page, kidName)).toHaveCount(0); // it left the pending queue

  // School A can no longer read the student; School B can, and sees where the student came from.
  await signIn(page, a.coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  expect((await page.request.get(`/api/v1/school/students/${kid.id}`)).status()).toBe(403);
  // ...and is told so: the requester's in-app notice is readable (a coordinator screen for it was missing until the second browser QA pass).
  await page.goto("/school/coordinator/notifications");
  await expect(page.getByText(new RegExp(`Transfer approved: ${kidName} moved to ${b.name}`))).toBeVisible();
  await signIn(page, b.coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  await page.goto(`/school/coordinator/students/${kid.id}`);
  await expect(page.getByRole("heading", { name: "Transfer history" })).toBeVisible();
  await expect(page.getByText(new RegExp(`Moved from ${a.name} to ${b.name}`))).toBeVisible();
  await page.goto("/school/coordinator/notifications");
  await expect(page.getByText(new RegExp(`${kidName} has joined ${b.name}`))).toBeVisible();

  // The parent (account created at School A) still reaches the child at School B, and sees the transfer.
  await signIn(page, parentEmail, PARENT_PASSWORD, "**/school/parent/dashboard");
  await expect(page.getByRole("heading", { name: kidName })).toBeVisible();
  await page.click(`a:has-text("View full profile & progress")`);
  await page.waitForURL(`**/school/parent/children/${kid.id}`);
  await expect(page.getByRole("heading", { name: "Transfer history" })).toBeVisible();
  await expect(page.getByText(new RegExp(`Moved from ${a.name} to ${b.name}`))).toBeVisible();

  // Responsive (RESPONSIVE_RULES): no horizontal scroll at 320 / 768 / 1024 / 1440 on both new screens.
  for (const [who, email, password, landing, path] of [
    ["coordinator", b.coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard", "/school/coordinator/transfers"],
    ["admin", ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard", "/overseas/admin/school-transfers"],
  ] as const) {
    await signIn(page, email, password, landing);
    await page.goto(path);
    for (const width of [320, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `${who}: horizontal overflow at ${width}px` }).toBe(true);
    }
  }
  await page.setViewportSize({ width: 1280, height: 720 });

  expect(pageErrors).toEqual([]);
});

test("a coordinator cannot reach another role's screens, and a stranger is sent to sign in (ENH-005)", async ({ page }) => {
  await signIn(page, "school.parent@edusphere.local", "Demo@123", "**/school/parent/dashboard");
  await page.goto("/school/coordinator/transfers");
  await expect(page.getByText("School Coordinator role required")).toBeVisible();
  expect((await page.request.get("/api/v1/overseas-admin/school-transfer-requests")).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/admin/school-transfers");
  await page.waitForURL(/\/overseas\/login/);
});
