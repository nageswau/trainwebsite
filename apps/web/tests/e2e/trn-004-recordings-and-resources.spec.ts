import { test, expect } from "@playwright/test";

// TRN-004 -- Recording list and resource upload. Both halves already worked (built for
// TRN-003 and reused generically) but had no E2E coverage of the trainer's own attach/
// upload actions in `TeacherWorkspaceActions.tsx`. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied (seeds the demo
// trainer's batch and live session).

test("trainer attaches a recording and the student sees it (TRN-004-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  // Schedule a fresh session rather than reusing the seeded "FastAPI APIs - Live
  // Session" -- that one is shared, permanent seed data another spec
  // (stu-003-live-classes.spec.ts) depends on staying recording-free.
  const sessionTitle = `TRN-004 E2E Session ${Date.now()}`;
  await page.goto("/it/trainer/live-sessions");
  const scheduleCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Schedule live session" }) });
  await scheduleCard.getByLabel("Batch").selectOption({ index: 1 });
  await scheduleCard.getByLabel("Session title").fill(sessionTitle);
  await scheduleCard.getByLabel("Starts").fill("2027-01-10T10:00");
  await scheduleCard.getByLabel("Ends").fill("2027-01-10T11:00");
  await scheduleCard.getByLabel("Meeting provider").selectOption("manual");
  await scheduleCard.getByLabel("Existing meeting URL, if applicable").fill("https://meet.example.com/e2e-session");
  await scheduleCard.getByRole("button", { name: "Schedule session" }).click();
  await expect(page.getByText("Live session scheduled.")).toBeVisible();

  const recordingCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Attach provider recording" }) });
  const sessionSelect = recordingCard.getByLabel("Live session");
  const optionValue = await sessionSelect.locator("option", { hasText: sessionTitle }).getAttribute("value");
  await sessionSelect.selectOption(optionValue!);
  await recordingCard.getByLabel("Recording URL").fill("https://provider.example.com/e2e-recording");
  await recordingCard.getByRole("button", { name: "Attach recording" }).click();
  // The success/error status renders once, shared above the whole action panel, not
  // nested inside each individual `.action-card` -- assert at the page level.
  await expect(page.getByText("Provider recording attached.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/course");
  // Repeated runs each schedule their own new session with a recording, so more than
  // one "Watch recording" link can legitimately accumulate here -- assert at least one.
  await expect(page.getByRole("link", { name: "Watch recording" }).first()).toBeVisible();
});

test("trainer publishes a resource and the enrolled student can see it (TRN-004-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  const resourceTitle = `TRN-004 E2E Resource ${Date.now()}`;
  await page.goto("/it/trainer/materials");
  const materialCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Publish course material" }) });
  await materialCard.getByLabel("Batch").selectOption({ index: 1 });
  await materialCard.getByLabel("Title").fill(resourceTitle);
  await materialCard.getByLabel("Resource URL").fill("https://example.com/e2e-notes.pdf");
  await materialCard.getByRole("button", { name: "Publish material" }).click();
  await expect(page.getByText("Material published.")).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/downloads");
  await expect(page.locator("table")).toContainText(resourceTitle);
});

test("live-session recording endpoint requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/live-sessions");
  await expect(page).toHaveURL(/\/it\/login/);
});
