import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-030 -- daily class attendance (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md, AC01, AC08, AC09, AC12).
// Setup is API-only (the enh-013 pattern): a throwaway school, an assigned teacher, two students (one with a linked parent). The
// feature -- marking the class, then reading it as the parent and in the 360 view -- is driven through the real UI.

const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh030-e2e-${who}-${unique}@example.local`;
const ctx = { studentId: "" };
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()} ${await res.text()}`);
  return api;
}

async function acceptInvite(token: string) {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post(`/api/v1/school/invites/${token}/accept`, { data: { password: INVITE_PASSWORD } });
  if (!res.ok()) throw new Error(`accept invite: ${res.status()} ${await res.text()}`);
  await api.dispose();
}

async function signIn(page: Page, address: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-030 daily class attendance", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E Attendance School ${unique}`, coordinator_full_name: "E2E Att Coordinator", coordinator_email: email("coord"), tier: "platinum" }); // ENH-022: marking needs a valid partnership tier
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const invite = await coord.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Att Teacher", email: email("teacher") } });
    await acceptInvite((await invite.json()).development_invite_token);
    const first = await coord.post("/api/v1/school/students", { data: { full_name: "Asha Attend", grade_or_class: "Grade 5", assigned_teacher_email: email("teacher"), parent_name: "E2E Att Parent", parent_email: email("parent") } });
    expect(first.status()).toBe(201);
    const student = await first.json();
    ctx.studentId = student.id;
    const second = await coord.post("/api/v1/school/students", { data: { full_name: "Ben Attend", grade_or_class: "Grade 5", assigned_teacher_email: email("teacher") } });
    expect(second.status()).toBe(201);
    await coord.dispose();
    await acceptInvite(student.development_invite_token);
  });

  test("the teacher marks the whole class with one Save (AC01, AC12)", async ({ page }) => {
    await signIn(page, email("teacher"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.getByRole("link", { name: "Attendance" }).first().click();
    await page.waitForURL("**/school/teacher/attendance");
    await expect(page.getByRole("heading", { level: 1, name: "Attendance" })).toBeVisible();
    await expect(page.getByRole("group")).toHaveCount(2);
    await page.getByRole("button", { name: "Mark all present" }).click();
    await page.getByRole("group", { name: /Ben Attend/ }).getByLabel("Absent").check();
    await page.getByRole("button", { name: "Save attendance" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Attendance saved for 2 students" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("group", { name: /Ben Attend/ }).getByLabel("Absent")).toBeChecked();
    await expect(page.getByRole("group", { name: /Asha Attend/ }).getByLabel("Present")).toBeChecked();
  });

  test("the attendance page fits a phone (AC12)", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await signIn(page, email("teacher"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.goto("/school/teacher/attendance");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("the parent sees it on the dashboard card (AC08)", async ({ page }) => {
    await signIn(page, email("parent"), INVITE_PASSWORD, "/school/parent/dashboard");
    await expect(page.getByText("Attendance (last 1 marked day)")).toBeVisible();
    await expect(page.getByText("1 present · 0 late · 0 absent · 0 excused")).toBeVisible();
  });

  test("the 360 Attendance tab shows the day and no longer says 'not tracked' (AC09)", async ({ page }) => {
    await signIn(page, email("teacher"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.goto(`/school/teacher/students/${ctx.studentId}/360`);
    await page.getByRole("tab", { name: /^Attendance/ }).click();
    const panel = page.getByRole("tabpanel");
    await expect(panel.getByRole("table", { name: "Daily attendance" })).toContainText("Present");
    await expect(panel).not.toContainText("not tracked yet (ENH-030)");
  });
});
