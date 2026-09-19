import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-007 -- Parent Portal: child 360 overview + parent notifications. Builds its own
// throwaway school + roster through the real onboarding/roster flows, has the Parent accept
// their invite, then confirms (a) a session scheduled by the Coordinator reaches the Parent
// as an in-app notification and as an upcoming session, (b) the child page shows every
// confirmed section, and (c) a sibling the Parent is NOT linked to is denied even by
// direct URL (SCH-001-AC03).

test("parent sees child overview, upcoming session, and notification; unlinked child denied (Parent Portal)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch007-e2e-coord-${unique}@example.local`;
  const parentEmail = `sch007-e2e-parent-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Parent Portal School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E PP Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  // Linked child (parent_email on the roster row issues the Parent invite automatically)
  // and an unlinked sibling at the same school for the deny check.
  const linkedRes = await page.request.post("/api/v1/school/students", { data: { full_name: "PP Linked Child", grade_or_class: "Grade 8", parent_name: "E2E PP Parent", parent_email: parentEmail } });
  expect(linkedRes.status()).toBe(201);
  const linked = await linkedRes.json();
  const parentToken = linked.development_invite_token;
  expect(parentToken).toBeTruthy();
  const unlinkedRes = await page.request.post("/api/v1/school/students", { data: { full_name: "PP Unlinked Sibling", grade_or_class: "Grade 10" } });
  const unlinked = await unlinkedRes.json();

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await expect(page.getByRole("heading", { name: "PP Linked Child" })).toBeVisible();
  await expect(page.getByText("No notifications yet.")).toBeVisible();

  // Coordinator now schedules a session -> the (now existing) Parent is notified.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
  const when = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();
  const activityRes = await page.request.post("/api/v1/school/activities", { data: { title: `PP Career Workshop ${unique}`, scheduled_at: when } });
  expect(activityRes.status()).toBe(201);

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", parentEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/parent/dashboard");

  // Dashboard: the one linked child (never the sibling), honest not-started statuses, the
  // upcoming session, and the notification the schedule generated.
  await expect(page.getByRole("heading", { name: "PP Linked Child" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "PP Unlinked Sibling" })).toHaveCount(0);
  await expect(page.getByText("Not started").first()).toBeVisible();
  await expect(page.getByText(`PP Career Workshop ${unique}`).first()).toBeVisible();
  await expect(page.getByText(`Upcoming session: PP Career Workshop ${unique}`)).toBeVisible();
  await expect(page.getByText("1 unread")).toBeVisible();

  // Full child page: every confirmed section is present.
  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${linked.id}`);
  for (const heading of ["Career guidance", "Counselling", "Recommended careers", "Psychometric assessment", "Academic results", "Activities", "Upcoming sessions"]) {
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
  await expect(page.getByText("No published results yet")).toBeVisible();

  // Notifications page lists the same event.
  await page.goto("/school/parent/notifications");
  await expect(page.getByText(`Upcoming session: PP Career Workshop ${unique}`)).toBeVisible();

  // Deny path: the sibling's page by direct URL.
  await page.goto(`/school/parent/children/${unlinked.id}`);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "PP Unlinked Sibling" })).toHaveCount(0);
});
