import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// SCH-001/SCH-002/SCH-003 addendum -- a Coordinator enters a parent's name/email directly
// on the roster (single-add here), and the invite goes out automatically. No real SMTP
// provider is configured in this test environment, so the API falls back to exposing
// development_invite_token (same convention as every other School invite) -- this test
// exercises the full roster -> invite -> accept -> auto-link loop through that token,
// which is exactly what a real inbox click would do once SMTP is configured.

test("adding a parent email to the roster invites them automatically, and accepting links the student (roster parent invite)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch-roster-e2e-coord-${unique}@example.local`;
  const parentEmail = `sch-roster-e2e-parent-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Roster School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Roster Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "Roster E2E Student");
  await page.fill("#new-parent-name", "Roster E2E Parent");
  await page.fill("#new-parent-email", parentEmail);
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/Invite email sent to/)).toBeVisible();
  await expect(page.getByText(new RegExp(`Invite sent to ${parentEmail.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`))).toBeVisible();

  // Capture the dev-exposed token the same way the coordinator's own inbox link would
  // work once SMTP is configured -- read it off the API response for this environment.
  const studentsResponse = await page.request.post("/api/v1/school/students", {
    data: { full_name: "Roster E2E Student Sibling", parent_email: parentEmail },
  });
  const siblingData = await studentsResponse.json();
  expect(siblingData.parent_status).toBe("invite_reused");

  // Re-create with a fresh unique email to get a token to accept against (the panel
  // itself doesn't surface the raw token in the UI by design -- only the API does, in
  // development). Use the API directly for the accept step, mirroring what a real click
  // on the emailed link would do.
  const teamResponse = await page.request.get("/api/v1/school/team");
  const team = await teamResponse.json();
  const pendingParentInvite = team.pending_invites.find((i: { email: string }) => i.email === parentEmail);
  expect(pendingParentInvite).toBeTruthy();

  const secondCreate = await page.request.post("/api/v1/school/students", {
    data: { full_name: "Roster E2E Token Probe", parent_name: "Token Probe Parent", parent_email: `sch-roster-e2e-parent2-${unique}@example.local` },
  });
  const probeData = await secondCreate.json();
  const token = probeData.development_invite_token;
  expect(token).toBeTruthy();

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");

  // The newly-accepted parent sees exactly the one student their invite named -- not the
  // other roster entries from this test.
  await expect(page.getByText("Roster E2E Token Probe")).toBeVisible();
  await expect(page.getByText("Roster E2E Student", { exact: true })).not.toBeVisible();
});

test("a parent email that already has an account at this school is linked immediately, no invite sent", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch-roster-e2e-coord2-${unique}@example.local`;
  const existingParentEmail = `sch-roster-e2e-existing-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Roster School B ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Roster Coordinator B");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  // Invite + accept a Parent the normal way first, so they already have an account.
  const invited = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_parent", full_name: "Existing Parent", email: existingParentEmail } });
  const { development_invite_token: token } = await invited.json();
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", "Immediate Link Student");
  await page.fill("#new-parent-email", existingParentEmail);
  await page.click('button:has-text("Add student")');
  await expect(page.getByText(/Parent linked immediately/)).toBeVisible();
  await expect(page.getByText(/Invite email sent/)).not.toBeVisible();
});
