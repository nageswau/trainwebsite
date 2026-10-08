import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-010 (AC1-AC4, P1): a partnership manager plans a UK visit from the university page, cannot approve or book it, submits it; the
// reporting head approves it from the queue; the manager confirms the date (the approved plan is locked), books travel, completes it
// with the follow-up date (AC3), starts the follow-up and closes it; the history shows every step; the pages fit a phone. Throwaway
// accounts via the real admin API.

const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc010-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc010-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U10-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Visits University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await post(`/api/v1/partnership/universities/${university.id}/contacts`, { name: "Priya Raman", designation: "Regional Manager – India" });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, university };
}

test("a UK visit goes from plan to closed with the head's approval", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, manager, university } = await setUp(page, stamp);

  // P1: the owning manager plans it from the university page.
  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.getByRole("link", { name: "University Visits" }).first().click();
  await expect(page.getByRole("heading", { name: "University visits" })).toBeVisible();
  await page.goto(`/partnership/universities/${university.id}`);
  const visits = page.getByRole("region", { name: "Visits" });
  await expect(visits.getByText("No visits planned yet.")).toBeVisible();
  await visits.getByRole("link", { name: "Plan a visit" }).click();
  await expect(page.getByRole("heading", { name: "Plan a university visit" })).toBeVisible();
  await page.getByRole("button", { name: "Save visit" }).click();
  await expect(page.getByText("Visit purpose is required")).toBeVisible();
  await page.getByLabel("Visit purpose (required)").fill("MoU discussion and the September intake");
  await page.getByLabel("Proposed visit date (required)").fill(today);
  await page.getByLabel("Travel required").check();
  await page.getByLabel("Travel notes").fill("Flight DEL-LHR");
  await page.getByLabel(/Priya Raman/).check();
  await page.getByLabel("Agenda").fill("1. MoU\n2. Scholarships");
  await page.getByRole("button", { name: "Save visit" }).click();
  await page.waitForURL(/\/partnership\/visits\/[0-9a-f-]{36}$/);
  const detail = page.url();
  await expect(page.getByRole("heading", { name: `Visit to ${university.name}` })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Status: Planned · Draft" })).toBeVisible();
  await expect(page.getByText("Priya Raman (Regional Manager – India)")).toBeVisible();

  // AC1 / AC2: a manager has no Approve, and nothing books before approval.
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mark travel booked" })).toHaveCount(0);
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByRole("status")).toHaveText("Submitted for approval.");
  await expect(page.getByRole("heading", { name: "Status: Planned · Waiting for approval" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Edit" })).toHaveCount(0);

  // The reporting head approves from the queue.
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.getByRole("link", { name: "Visit approvals" }).first().click();
  const queue = page.getByRole("region", { name: "Visits waiting for approval" });
  await queue.getByRole("row").filter({ hasText: university.name }).getByRole("link").click();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("status")).toHaveText("Visit approved; the manager has been told.");
  await expect(page.getByRole("heading", { name: "Status: Approved" })).toBeVisible();

  // The manager confirms the date: the approved plan is locked.
  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.goto(detail);
  await page.getByRole("link", { name: "Edit" }).click();
  await expect(page.getByLabel("Visit purpose (required)")).toBeDisabled();
  await page.getByLabel("Confirmed visit date").fill(today);
  await page.getByLabel("Hotel notes").fill("Booked: Hotel near campus");
  await page.getByRole("button", { name: "Save visit" }).click();
  await page.waitForURL(detail);

  // Travel booked, then completed with the follow-up date (AC3), follow-up, closed.
  await page.getByRole("button", { name: "Mark travel booked" }).click();
  await expect(page.getByRole("heading", { name: "Status: Travel Booked" })).toBeVisible();
  await page.getByRole("button", { name: "Mark visit completed" }).click();
  await page.getByRole("button", { name: "Confirm completed" }).click();
  await expect(page.getByText("Choose the follow-up date")).toBeVisible();
  await page.getByLabel("Follow-up date").fill(inDays(7));
  await page.getByRole("button", { name: "Confirm completed" }).click();
  await expect(page.getByRole("heading", { name: "Status: Visit Completed" })).toBeVisible();
  await page.getByRole("button", { name: "Start follow-up" }).click();
  await expect(page.getByRole("heading", { name: "Status: Follow-up" })).toBeVisible();
  await page.getByRole("button", { name: "Close visit" }).click();
  await page.getByRole("button", { name: "Confirm close" }).click();
  await expect(page.getByRole("heading", { name: "Status: Closed" })).toBeVisible();

  // AC4: every step is in the history.
  const history = page.getByRole("region", { name: "History" });
  for (const step of ["Planned", "Submitted for approval", "Approved", "Edited", "Travel booked", "Visit completed", "Follow-up started", "Closed"]) {
    await expect(history.getByText(step, { exact: true })).toBeVisible();
  }

  // Phone width: the detail and the list fit without sideways scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of [detail, "/partnership/visits?mine=true"]) {
    await page.goto(path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});
