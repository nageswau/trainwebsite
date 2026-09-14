import { test, expect } from "@playwright/test";

// STU-003 -- Live class access. Requires the stack running via `docker compose up`
// with `python -m app.seed` already applied (seeds a live session for the demo student).

async function loginAsSeededStudent(page: import("@playwright/test").Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
}

test("student sees a real, clickable join button for their scheduled live class (STU-003-AC01)", async ({ page }) => {
  // A real <button> (not a link) as of the join-experience fix in
  // `docs/decisions/PENDING_ZOHO_LIVE_CLASSES.md` §1b -- a click is intercepted for
  // time-window gating and (for a participant) an identity confirmation before the real
  // URL ever opens, so this can no longer be a plain href. See
  // `join-session-button.spec.ts` for the gating/confirmation behavior itself, exercised
  // against controlled fixture data rather than the shared, timing-fragile seeded session.
  await loginAsSeededStudent(page);
  await page.goto("/it/student/course");
  await expect(page.getByRole("heading", { name: "Live classes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Join class" }).first()).toBeVisible();
});

test("a session with no recording yet shows a clear message, not a broken page (STU-003-AC02)", async ({ page }) => {
  await loginAsSeededStudent(page);
  await page.goto("/it/student/course");
  await expect(page.getByText("Recording not available for this session.").first()).toBeVisible();
});

test("live classes panel requires no manual reference typing -- unlike the old text panel", async ({ page }) => {
  await loginAsSeededStudent(page);
  await page.goto("/it/student/course");
  // The session card itself carries the title/provider/time -- nothing here should be
  // a raw pipe-delimited string dump (the old "Live classes" panel format).
  await expect(page.locator("body")).not.toContainText("| Join:");
});

test("live class information requires authentication", async ({ page }) => {
  await page.goto("/it/student/course");
  await expect(page).toHaveURL(/\/it\/login/);
});
