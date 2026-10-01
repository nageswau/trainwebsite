import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { activateWithToken, E2E_PASSWORD } from "./helpers/welcome";

// AGN-004 -- a Master's students with no login: create, duplicate warning, edit, archive, unarchive, assign; keyboard-only; 320 px.
// Uses the seeded demo agent (a Master of an active agency); the assignment test registers its own agency and Staff member
// (AGN-002's staff logins). Unique names per run: the E2E database is shared and keeps rows.

async function signInAsDemoAgent(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
}

async function signIn(page: Page, email: string, password: string, landing = "/overseas/agent/dashboard") {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

// The staff-create response never carries the link token (AGN-002 S3); activate the way an admin re-send does in dev/test.
async function adminActivate(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=agent&provisioning_status=pending_setup")).json();
  const staff = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${staff.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function addStudent(page: Page, name: string, email?: string) {
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  if (email) await form.getByLabel("Email").fill(email);
  await form.getByRole("button", { name: "Save student" }).click();
  return form;
}

test("a Master adds, edits, archives and restores a student with no login (AGN-004-AC01/03/04/08)", async ({ page }) => {
  const id = stamp();
  const name = `E2E Student ${id}`;
  const email = `agn004-${id}@example.local`;
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  const students = page.getByRole("list", { name: "Students" });

  await addStudent(page, name, email);
  await expect(page.getByText(`${name} added.`)).toBeVisible();

  // Same email in another case: the within-agency duplicate warning, then Save anyway.
  const twin = await addStudent(page, `${name} Twin`, email.toUpperCase());
  await expect(twin.getByRole("alert")).toContainText("already exists in your agency");
  await twin.getByRole("button", { name: "Save anyway" }).click();
  await expect(page.getByText(`${name} Twin added.`)).toBeVisible();

  // The search is debounced: wait until the list holds exactly this run's two students before acting on a card.
  await page.getByLabel("Search students").fill(id);
  await expect(students.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("region", { name: "Student list" })).toHaveAttribute("aria-busy", "false");
  await students.getByRole("button", { name: `View ${name}`, exact: true }).click();
  const detail = page.getByRole("region", { name, exact: true });
  await detail.getByRole("button", { name: "Edit" }).click();
  await detail.getByLabel("Preferred country").fill("Ireland");
  await detail.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText(`${name} saved.`)).toBeVisible();
  await expect(detail.getByText("Ireland")).toBeVisible();

  await students.getByRole("button", { name: `Archive ${name}`, exact: true }).click();
  await students.getByRole("button", { name: "Confirm archive" }).click();
  await expect(page.getByText(`${name} archived.`)).toBeVisible();
  await expect(students.getByRole("heading", { name, exact: true })).toHaveCount(0);

  await page.getByLabel("Show archived").check();
  await students.getByRole("button", { name: `Unarchive ${name}`, exact: true }).click();
  await students.getByRole("button", { name: "Confirm unarchive" }).click();
  await expect(page.getByText(`${name} restored.`)).toBeVisible();
});

test("the Students page leads with all students, full width; the roster is a separate application-status table (browser QA-01/02)", async ({ page }) => {
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  const panelHeading = page.getByRole("heading", { name: "All students", level: 3 });
  const rosterHeading = page.getByRole("heading", { name: "Application status", level: 2 });
  await expect(panelHeading).toBeVisible();
  await expect(rosterHeading).toBeVisible();
  const panelTop = (await panelHeading.boundingBox())!.y;
  const rosterTop = (await rosterHeading.boundingBox())!.y;
  expect(panelTop).toBeLessThan(rosterTop);
  const widths = await page.evaluate(() => {
    const panel = document.querySelector(".agent-students")!.getBoundingClientRect().width;
    const content = document.querySelector(".action-grid")!.getBoundingClientRect().width;
    return { panel, content };
  });
  expect(widths.panel).toBeGreaterThan(widths.content * 0.9);
  // The link form for students with an account is still on the page, and the roster still lists them.
  await expect(page.getByRole("button", { name: "Link student" })).toBeVisible();
  await expect(page.locator("table tbody tr", { hasText: "Ananya Sharma" })).toBeVisible();
});

test("keyboard only: add a student (AGN-004-AC13)", async ({ page }) => {
  const name = `Keyboard ${stamp()}`;
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("form", { name: "Add student" }).getByLabel("Full name (required)").focus();
  await page.keyboard.type(name);
  await page.keyboard.press("Enter");
  await expect(page.getByText(`${name} added.`)).toBeVisible();
});

test("320 px: the Students page has no horizontal overflow (AGN-004-AC13)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signInAsDemoAgent(page);
  await page.goto("/overseas/agent/students");
  await expect(page.getByRole("heading", { name: "All students", level: 3 })).toBeVisible();
  await expect(page.getByRole("list", { name: "Students" }).or(page.getByText(/No students yet/))).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

// AC09 / spec §6: a Master assigns a student to a named Staff member in the UI, and that Staff member then sees it. A fresh
// agency (the AGN-002 spec's flow) keeps the staff list short and independent of earlier runs.
test("a Master assigns a student to a Staff member, who then sees it (AGN-004-AC09)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const id = stamp();
  const agency = `Tau Overseas ${id}`;
  const masterEmail = `agn004-m-${id}@example.local`;
  const staffEmail = `agn004-s-${id}@example.local`;
  const name = `Assign Me ${id}`;

  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Tau Master");
  await page.fill('input[name="email"]', masterEmail);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  await page.locator(".card", { hasText: agency }).getByRole("button", { name: "Approve" }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  const staffForm = page.getByRole("form", { name: "Add a staff member" });
  await staffForm.getByLabel("Full name").fill("Tau Staff");
  await staffForm.getByLabel("Email").fill(staffEmail);
  await staffForm.getByRole("button", { name: "Add staff" }).click();
  const created = await page.getByText(/-S001 created/).textContent();
  const code = created!.match(/(\S+-S001)/)![1];

  await page.goto("/overseas/agent/students");
  await addStudent(page, name);
  await expect(page.getByText(`${name} added.`)).toBeVisible();
  await page.getByRole("button", { name: `Assign ${name}`, exact: true }).click();
  const choice = page.getByRole("group", { name: `Assign ${name}` });
  await choice.getByLabel("Assign to").selectOption({ label: `${code} · Tau Staff` });
  await choice.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByText(`${name} assigned to ${code} · Tau Staff.`)).toBeVisible();
  await expect(page.getByRole("list", { name: "Students" }).getByRole("listitem").filter({ hasText: name })).toContainText(`${code} · Tau Staff`);

  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("list", { name: "Students" }).getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(staff.getByRole("button", { name: `Assign ${name}` })).toHaveCount(0);
  await staff.context().close();
});
