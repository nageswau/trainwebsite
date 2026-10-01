import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { pickFromList } from "./helpers/pick";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-020 (docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md, AC16, AC20; DEC-SCOPE-043): a counsellor opens
// an education-loan case through the real form, advances it one stage with the keyboard, closes it with a reason; the parent sees the
// case read-only; an assigned teacher is refused. Setup is API-only on a throwaway Platinum school, like enh-026/enh-030.
const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh020-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const schoolName = `E2E 020 School ${unique}`;
const ctx = { studentName: `Asha 020 ${unique}`, parentEmail: email("parent"), studentId: "" };

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()} ${await res.text()}`);
  return api;
}

async function acceptInvite(token: string) {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post(`/api/v1/school/invites/${token}/accept`, { data: { password: INVITE_PASSWORD } });
  expect(res.ok()).toBeTruthy();
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

test.describe.serial("ENH-020 funding support cases", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: schoolName, coordinator_full_name: "E2E 020 Coordinator", coordinator_email: email("coord"), tier: "platinum" });
    await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role: "career_counselor", full_name: "E2E 020 Counselor", email: email("counselor"), school_ids: [school.id] });
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const invite = await coord.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E 020 Teacher", email: email("teacher") } });
    await acceptInvite((await invite.json()).development_invite_token);
    const created = await coord.post("/api/v1/school/students", { data: { full_name: ctx.studentName, grade_or_class: "Grade 11", assigned_teacher_email: email("teacher"), parent_name: "E2E 020 Parent", parent_email: ctx.parentEmail } });
    expect(created.status()).toBe(201);
    const student = await created.json();
    ctx.studentId = student.id;
    await coord.dispose();
    await acceptInvite(student.development_invite_token);
  });

  test("counsellor opens a case, advances it with the keyboard, then closes it with a reason (AC16)", async ({ page }) => {
    await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
    await page.getByRole("link", { name: "Funding" }).first().click();
    await page.waitForURL("**/school/career-counselor/funding");
    await expect(page.getByText("No funding support cases yet.", { exact: false })).toBeVisible();

    const add = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add a case" }) });
    await pickFromList(add.getByRole("combobox", { name: "Student" }), ctx.studentName, `${ctx.studentName} — ${schoolName}`);
    await add.getByLabel("Support type").selectOption("education_loan");
    await add.getByLabel("Provider or institution (optional)").fill("State Bank of India");
    await add.getByLabel("Amount (optional)").fill("₹5,00,000");
    await add.getByRole("button", { name: "Add case" }).click();
    await expect(add.getByRole("status")).toHaveText("Case saved.");
    const open = page.getByRole("table", { name: "Open cases" });
    await expect(open.getByText("Stage 1 of 6 · Required")).toBeVisible();

    // A second open education-loan case for the same student is refused in words, not silently duplicated.
    await pickFromList(add.getByRole("combobox", { name: "Student" }), ctx.studentName, `${ctx.studentName} — ${schoolName}`);
    await add.getByLabel("Support type").selectOption("education_loan");
    await add.getByRole("button", { name: "Add case" }).click();
    await expect(add.getByRole("alert")).toContainText("already has an open education loan case");

    const edit = open.getByRole("button", { name: `Edit education loan case for ${ctx.studentName}` });
    await edit.focus();
    await page.keyboard.press("Enter");
    const heading = page.getByRole("heading", { name: `Update ${ctx.studentName}'s education loan case` });
    await expect(heading).toBeFocused();
    const card = page.locator(".action-card", { has: heading });
    await card.getByLabel("Stage").selectOption("counselling");
    await card.getByRole("button", { name: "Save changes" }).click();
    await expect(open.getByText("Stage 2 of 6 · Counselling")).toBeVisible();
    await expect(open.getByRole("button", { name: `Edit education loan case for ${ctx.studentName}` })).toBeFocused();

    await page.keyboard.press("Enter");
    await card.getByLabel("Stage").selectOption("closed");
    await expect(card.getByLabel("Reason for closing")).toBeFocused();
    await page.keyboard.type("Family chose another lender");
    await card.getByRole("button", { name: "Save changes" }).click();
    const finished = page.locator("details.funding-finished");
    await expect(finished.locator("summary")).toHaveText("Finished cases (1)");
    await finished.locator("summary").click();
    await expect(finished.getByText("Family chose another lender")).toBeVisible();
    await expect(finished.getByRole("button")).toHaveCount(0);
  });

  test("the parent sees the case read-only (AC16)", async ({ page }) => {
    await signIn(page, ctx.parentEmail, INVITE_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    const card = page.locator(".funding-card");
    await expect(card.getByRole("heading", { name: "Funding support" })).toBeVisible();
    await expect(card.getByText("Education loan")).toBeVisible();
    await expect(card.getByText("Family chose another lender")).toBeVisible();
    await expect(card.getByRole("button")).toHaveCount(0);
  });

  test("an assigned teacher is refused the funding cases (AC11)", async () => {
    const teacher = await apiAs(email("teacher"), INVITE_PASSWORD);
    const res = await teacher.get(`/api/v1/school/students/${ctx.studentId}/funding-records`);
    expect(res.status()).toBe(403);
    expect((await res.json()).detail).toBe("Funding support cases are not visible to teachers.");
    await teacher.dispose();
  });

  for (const width of [320, 768]) {
    test(`funding page stacks rows and has no page-level horizontal overflow at ${width}px (AC20)`, async ({ page }) => {
      const counselor = await apiAs(email("counselor"), E2E_PASSWORD);
      const reopened = await counselor.post("/api/v1/school/funding-records", { data: { school_student_id: ctx.studentId, support_type: "scholarship", provider_name: "A-deliberately-long-unbroken-provider-name-0123456789" } });
      expect([201, 409]).toContain(reopened.status());
      await counselor.dispose();
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
      await page.goto("/school/career-counselor/funding");
      await expect(page.getByRole("heading", { name: "Open cases" })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      if (width === 320) {
        const editButton = page.getByRole("button", { name: /^Edit scholarship case for / });
        expect((await editButton.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
        await expect(page.locator("table.funding-records thead")).toHaveCSS("position", "absolute");
      }
    });
  }
});
