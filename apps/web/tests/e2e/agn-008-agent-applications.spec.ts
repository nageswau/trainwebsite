import { expect, test, type Page } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-008 -- an agency's applications for students with no login: create with ID/dates, edit, forward-only status, withdraw;
// sidebar filters; staff scope; the admin and university_rep lists name the owner; 320 px. Unique names per run (shared E2E DB).
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function addNoLoginStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

async function manchesterId(page: Page): Promise<string> {
  const universities = await (await page.request.get("/api/v1/public/universities")).json();
  return universities.find((u: { slug: string }) => u.slug === "university-of-manchester").id;
}

async function createApplication(page: Page, name: string, reference: string) {
  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — no login$`));
  await page.locator("#agent-app-university").selectOption(await manchesterId(page));
  await page.getByLabel("Application ID").fill(reference);
  await page.getByLabel("Offer deadline").fill("2027-01-15");
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Application created." })).toBeVisible();
}

test("a Master creates, edits, moves forward and withdraws an application for a student with no login (AC01/04/05/06/11)", async ({ page }) => {
  const name = `E2E App ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await addNoLoginStudent(page, name);
  await createApplication(page, name, `REF-${stamp()}`);

  const sidebar = page.locator(".portal-nav");
  const list = page.getByRole("list", { name: "Applications", exact: true });
  const view = list.getByRole("button", { name: new RegExp(`^View ${name} — `) });
  await view.click();
  const detail = page.getByRole("region", { name: new RegExp(`^${name} — `) });
  await detail.getByRole("button", { name: "Edit" }).click();
  await detail.getByLabel("Intake (required)").fill("Spring 2028");
  await detail.getByRole("button", { name: "Save" }).click();
  await expect(detail.getByRole("status")).toHaveText("Saved.");

  await detail.getByLabel("Move to").selectOption("offer");
  await detail.getByRole("button", { name: "Update status" }).click();
  await expect(detail.getByRole("status")).toHaveText("Status updated to Offer.");
  const options = await detail.getByLabel("Move to").locator("option").allTextContents();
  expect(options).toEqual(["Visa documentation", "Status tracking"]); // never backward, never Enrolled

  await sidebar.getByRole("link", { name: "Offer received" }).click();
  await expect(page.getByRole("heading", { name: "Offer received" })).toBeVisible();
  await expect(sidebar.getByRole("link", { name: "Offer received" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("list", { name: "Applications", exact: true })).toContainText(name);

  await page.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  const again = page.getByRole("region", { name: new RegExp(`^${name} — `) });
  await again.getByRole("button", { name: "Withdraw application" }).click();
  await again.getByRole("button", { name: "Yes, withdraw" }).click();
  await expect(again.getByRole("status")).toHaveText("Application withdrawn.");
  await expect(again.getByText("This application is withdrawn, so it can no longer be changed.")).toBeVisible();
});

test("the admin and university_rep lists name a no-login owner (AC08)", async ({ page, request }) => {
  const name = `E2E Owner ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await addNoLoginStudent(page, name);
  await createApplication(page, name, `OWN-${stamp()}`);
  for (const [email, url] of [
    ["overseasadmin@edusphere.local", "/api/v1/admin/applications"],
    ["university.rep@edusphere.local", "/api/v1/workflows/overseas/applications"],
  ]) {
    expect((await request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division: "overseas" } })).ok()).toBeTruthy();
    const rows = await (await request.get(url)).json();
    expect(rows.map((r: { student: string }) => r.student)).toContain(name);
    await request.post("/api/v1/auth/logout");
  }
});

test("staff see only their assigned students' applications through the filters (AC02/AC11)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn008");
  const staffEmail = `agn008-s-${unique}@example.local`;
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  const staffForm = page.getByRole("form", { name: "Add a staff member" });
  await staffForm.getByLabel("Full name").fill("Apps Staff");
  await staffForm.getByLabel("Email").fill(staffEmail);
  await staffForm.getByRole("button", { name: "Add staff" }).click();
  const created = await page.getByText(/-S001 created/).textContent();
  const code = created!.match(/(\S+-S001)/)![1];

  const mine = `E2E Mine ${stamp()}`;
  const theirs = `E2E Theirs ${stamp()}`;
  await addNoLoginStudent(page, mine);
  await addNoLoginStudent(page, theirs);
  await createApplication(page, mine, `M-${stamp()}`);
  await createApplication(page, theirs, `T-${stamp()}`);
  // Assign `mine` to the staff member (AGN-004's assign control on the Students page).
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: `Assign ${mine}`, exact: true }).click();
  const choice = page.getByRole("group", { name: `Assign ${mine}` });
  await choice.getByLabel("Assign to").selectOption({ label: `${code} · Apps Staff` });
  await choice.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByText(`${mine} assigned to ${code} · Apps Staff.`)).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await staff.goto("/overseas/agent/applications?status=draft");
  const list = staff.getByRole("list", { name: "Applications", exact: true });
  await expect(list).toContainText(mine);
  await expect(list).not.toContainText(theirs);
  await staff.context().close();
});

test("no horizontal scroll at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await page.goto("/overseas/agent/applications");
  await expect(page.getByRole("heading", { name: "Applications", level: 2 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
