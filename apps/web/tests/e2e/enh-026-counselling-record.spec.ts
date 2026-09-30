import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { pickFromList } from "./helpers/pick";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-026 (docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md, AC26-1..AC26-8, AC-R5):
// a counsellor records a session through the real form, moves it Scheduled -> Completed with the keyboard, and the parent sees
// the status and structured fields. Setup is API-only on a throwaway school, like enh-013.
const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh026-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const schoolName = `E2E 026 School ${unique}`;
const ctx = { studentName: `Asha 026 ${unique}`, parentEmail: email("parent"), studentId: "" };

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()} ${await res.text()}`);
  return api;
}

async function signIn(page: Page, address: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-026 counselling record", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: schoolName, coordinator_full_name: "E2E 026 Coordinator", coordinator_email: email("coord") });
    const tier = await admin.patch(`/api/v1/overseas-admin/schools/${school.id}`, { data: { tier: "platinum" } });
    expect(tier.ok()).toBeTruthy();
    await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role: "career_counselor", full_name: "E2E 026 Counselor", email: email("counselor"), school_ids: [school.id] });
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const created = await coord.post("/api/v1/school/students", { data: { full_name: ctx.studentName, grade_or_class: "Grade 9", parent_name: "E2E 026 Parent", parent_email: ctx.parentEmail } });
    expect(created.status()).toBe(201);
    const student = await created.json();
    ctx.studentId = student.id;
    await coord.dispose();
    const accept = await playwrightRequest.newContext({ baseURL });
    const accepted = await accept.post(`/api/v1/school/invites/${student.development_invite_token}/accept`, { data: { password: INVITE_PASSWORD } });
    expect(accepted.ok()).toBeTruthy();
    await accept.dispose();
    // FV-03: a long unbroken note makes the Records table wider than a phone; the table must scroll inside its card,
    // not stretch the page.
    const counselor = await apiAs(email("counselor"), E2E_PASSWORD);
    const wide = await counselor.post("/api/v1/school/career-counselor/records", {
      data: { school_student_id: ctx.studentId, record_type: "recommendation", notes: "Recommendation-with-a-deliberately-long-unbroken-reference-code-0123456789" },
    });
    expect(wide.status()).toBe(201);
    await counselor.dispose();
  });

  test("counsellor schedules a session, then completes it with the keyboard", async ({ page }) => {
    await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
    const add = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add a record" }) });
    await pickFromList(add.getByRole("combobox", { name: "Student" }), ctx.studentName, `${ctx.studentName} — ${schoolName}`);
    await add.getByLabel("Type").selectOption("counselling_note");
    await add.getByLabel("Status").selectOption("scheduled");
    await add.getByLabel("Scheduled for").fill("2026-12-01T10:00");
    await add.getByLabel("Weak areas").fill("Essays, Time management");
    await add.getByRole("button", { name: "Save record" }).click();
    await expect(add.getByRole("status")).toHaveText("Record saved.");
    const row = page.getByRole("row", { name: new RegExp(ctx.studentName) });
    await expect(row.getByText("Scheduled", { exact: true })).toBeVisible();

    const edit = row.getByRole("button", { name: new RegExp(`^Edit counselling note of .+ for ${ctx.studentName}$`) });
    await edit.focus();
    await page.keyboard.press("Enter");
    const heading = page.getByRole("heading", { name: `Edit record for ${ctx.studentName}` });
    await expect(heading).toBeFocused();
    const card = page.locator(".action-card", { has: heading });
    await card.getByLabel("Status").selectOption("completed");
    await card.getByLabel("Notes").fill("Discussed essay practice.");
    await card.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("row", { name: new RegExp(ctx.studentName) }).getByText("Completed", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: new RegExp(`^Edit counselling note of .+ for ${ctx.studentName}$`) })).toBeFocused();
  });

  test("parent sees the completed counselling status and structured fields", async ({ page }) => {
    await signIn(page, ctx.parentEmail, INVITE_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    const counselling = page.locator(".card", { has: page.getByRole("heading", { name: "Counselling", exact: true }) });
    await expect(counselling.getByText("Completed", { exact: true })).toBeVisible();
    await expect(counselling.getByText("Weak areas")).toBeVisible();
    await expect(counselling.getByText("Essays, Time management")).toBeVisible();
  });

  for (const width of [320, 768, 1024, 1440]) {
    test(`counsellor screen has no page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
      await expect(page.getByRole("heading", { name: "Records" })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});
