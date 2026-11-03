import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-011: the IT counselor converts a Qualified lead in one step (account, enrolment, fee plan with installments, onboarding checklist);
// a duplicate IT student is offered and enrolled instead; the IT Admin converts from the leads table. Throwaway accounts; tablet and
// phone widths have no sideways scroll; no console errors. Screenshots go to test-results/itc-011-*.png.
test.describe.configure({ timeout: 240_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const istDay = (offset: number) => new Date(Date.now() + 5.5 * 3600_000 + offset * 86_400_000).toISOString().slice(0, 10);
const phone = () => `7${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;

async function world(page: Page) {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123");
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post("/api/v1/admin/users", { role: "telecaller_manager", division: "global", full_name: `E2E CV Manager ${stamp}`, email: `itc011-m-${stamp}@example.local` });
  const caller = await post("/api/v1/admin/users", {
    role: "telecaller", full_name: `E2E CV Telecaller ${stamp}`, email: `itc011-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `CV-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E CV Counselor ${stamp}`;
  const counselor = await post("/api/v1/admin/users", { role: "counselor", division: "it", full_name: counselorName, email: `itc011-c-${stamp}@example.local` });
  const other = await post("/api/v1/admin/users", { role: "counselor", division: "it", full_name: `E2E CV Other ${stamp}`, email: `itc011-o-${stamp}@example.local` });
  const admin = await post("/api/v1/admin/users", { role: "it_admin", division: "it", full_name: `E2E CV Admin ${stamp}`, email: `itc011-a-${stamp}@example.local` });
  const course = await post("/api/v1/telecaller/products", { group: "it", name: `Python Full Stack ${stamp}` });
  const twinPhone = phone();
  const twinName = `E2E CV Twin ${stamp}`;
  const twin = { full_name: twinName, ...(await post("/api/v1/admin/users", { role: "it_student", division: "it", full_name: twinName, email: `itc011-s-${stamp}@example.local`, phone: twinPhone })) };
  await page.request.post("/api/v1/auth/logout");
  for (const user of [caller, counselor, other, admin]) await activateWithToken(page.request, user.development_welcome_token);

  // the telecaller creates three leads and hands them to the counselor; the counselor moves them to Qualified
  await signIn(page, "it", caller.email, E2E_PASSWORD);
  const leads: string[] = [];
  for (const [n, mobile] of [[1, phone()], [2, twinPhone], [3, phone()]] as const) {
    const created = await page.request.post("/api/v1/telecaller/leads", { data: { name: `CV Lead ${n} ${stamp}`, email: `itc011-l${n}-${stamp}@example.local`, phone: mobile, product_id: course.id, source: "walk_in" } });
    expect(created.status(), await created.text()).toBe(201);
    const id = (await created.json()).id as string;
    const handed = await page.request.post(`/api/v1/telecaller/leads/${id}/handover`, { data: { counselor_id: counselor.id } });
    expect(handed.status(), await handed.text()).toBe(200);
    leads.push(id);
  }
  await signIn(page, "it", counselor.email, E2E_PASSWORD);
  for (const id of leads) {
    const moved = await page.request.post(`/api/v1/counselor/leads/${id}/stage`, { data: { to_stage: "qualified" } });
    if (moved.status() === 422) {  // an open target needs a next action first (ccrm-003 A1)
      expect((await page.request.put(`/api/v1/counselor/leads/${id}/next-action`, { data: { next_action: "Convert", next_action_due: istDay(1) } })).status()).toBe(200);
      expect((await page.request.post(`/api/v1/counselor/leads/${id}/stage`, { data: { to_stage: "qualified" } })).status()).toBe(200);
    } else expect(moved.status(), await moved.text()).toBe(200);
  }
  const record = await page.request.post(`/api/v1/counselor/leads/${leads[0]}/counseling`, { data: { outcome: "interested", fee_quoted: "45000.00", decision_maker: "parent" } });
  expect(record.status(), await record.text()).toBe(201);
  return { stamp, counselor, other, admin, twin, leads };
}

test("the IT counselor converts a lead in one step; a duplicate is enrolled instead; the IT Admin converts from the table", async ({ page }) => {
  const { stamp, counselor, other, admin, twin, leads } = await world(page);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && !/status of (4\d\d)/.test(m.text()) && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // --- happy path, with a two-part fee plan (desktop) ---
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/it/counselor/leads/${leads[0]}`);
  await page.getByRole("button", { name: "Convert to IT student" }).click();
  const form = page.getByRole("form", { name: "Convert to IT student" });
  await expect(form.getByLabel("Batch")).toBeVisible();
  await expect(form.getByLabel("Full name")).toHaveValue(`CV Lead 1 ${stamp}`);
  await expect(form.getByLabel("Fee (INR)")).toHaveValue("45000");
  await expect(form.getByText("Prefilled from the fee quoted in counseling.")).toBeVisible();
  await expect(form.getByRole("listitem").first()).toBeVisible(); // the checklist preview
  await form.getByRole("button", { name: "Add installment" }).click();
  await form.getByLabel("Installment 1 amount").fill("20000");
  await form.getByLabel("Installment 1 due date").fill(istDay(0));
  await form.getByRole("button", { name: "Convert and enrol" }).click();
  await expect(form.getByText("The installments must add up to the fee.")).toBeVisible(); // checked before sending
  await form.getByRole("button", { name: "Add installment" }).click();
  await form.getByLabel("Installment 2 amount").fill("25000");
  await form.getByLabel("Installment 2 due date").fill(istDay(30));
  await page.screenshot({ path: "test-results/itc-011-form-desktop.png", fullPage: true });
  const posts: string[] = [];
  page.on("request", (r) => r.method() === "POST" && r.url().endsWith("/convert-it") && posts.push(r.url()));
  await form.getByRole("button", { name: "Convert and enrol" }).dblclick(); // a double click converts once
  await expect(page.getByText(/Student account created and enrolled in .+ \(EDU-/)).toBeVisible();
  expect(posts).toHaveLength(1);
  await expect(page.getByText("Stage: Application/Enrollment")).toBeVisible();
  const checklist = page.getByRole("region", { name: "Onboarding checklist" });
  await expect(checklist.getByText(/0 of \d+ done/)).toBeVisible();
  await checklist.getByRole("checkbox").first().check();
  await expect(checklist.getByText(/1 of \d+ done/)).toBeVisible();
  await page.screenshot({ path: "test-results/itc-011-converted-desktop.png", fullPage: true });

  // refresh: the link and the ticked checklist stay; no second conversion is offered
  await page.reload();
  await expect(page.getByRole("region", { name: "Onboarding checklist" }).getByText(/1 of \d+ done/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Convert to IT student" })).toHaveCount(0);

  // the student's fee account holds the two installments (read as the counselor, linked by itc-003)
  const enrollmentId = (await (await page.request.get(`/api/v1/counselor/leads/${leads[0]}`)).json()).it_conversion.enrollment_id;
  const account = await (await page.request.get(`/api/v1/it/enrollments/${enrollmentId}/fee-account`)).json();
  expect(account.installments.map((i: { amount: number }) => i.amount)).toEqual([20000, 25000]);

  // --- another counselor: the lead and the checklist are out of reach ---
  await signIn(page, "it", other.email, E2E_PASSWORD);
  expect((await page.request.get(`/api/v1/counselor/leads/${leads[0]}/convert-it`)).status()).toBe(404);
  expect((await page.request.get(`/api/v1/it/enrollments/${enrollmentId}/onboarding`)).status()).toBe(404);

  // --- the duplicate: the lead's mobile belongs to an IT student, who is offered and enrolled (tablet) ---
  await signIn(page, "it", counselor.email, E2E_PASSWORD);
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto(`/it/counselor/leads/${leads[1]}`);
  await page.getByRole("button", { name: "Convert to IT student" }).click();
  const second = page.getByRole("form", { name: "Convert to IT student" });
  await expect(second.getByText("Prefilled from the course fee.")).toBeVisible();
  await second.getByRole("button", { name: "Convert and enrol" }).click();
  await expect(second.getByText("An IT student already has this email or mobile. Link the existing student instead.")).toBeVisible();
  await second.getByRole("group", { name: "Existing IT students" }).getByRole("button", { name: `Enrol ${twin.full_name}` }).click();
  await second.getByRole("button", { name: "Enrol existing student" }).click();
  await expect(page.getByText(`${twin.full_name} is enrolled in`, { exact: false })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
  await page.screenshot({ path: "test-results/itc-011-existing-tablet.png", fullPage: true });

  // --- phone width: the form fits ---
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/it/counselor/leads/${leads[2]}`);
  await page.getByRole("button", { name: "Convert to IT student" }).click();
  await page.getByRole("form", { name: "Convert to IT student" }).getByRole("button", { name: "Add installment" }).click();
  await expect(page.getByRole("form", { name: "Convert to IT student" }).getByLabel("Installment 1 amount")).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
  await page.screenshot({ path: "test-results/itc-011-form-phone.png", fullPage: true });
  await page.getByRole("form", { name: "Convert to IT student" }).getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("button", { name: "Convert to IT student" })).toBeVisible();

  // --- the IT Admin converts the third lead from the leads table (desktop) ---
  await signIn(page, "it", admin.email, E2E_PASSWORD);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/it/admin/leads?q=${encodeURIComponent(`CV Lead 3 ${stamp}`)}`);
  await page.getByRole("button", { name: `Convert CV Lead 3 ${stamp} to an IT student` }).click();
  const adminForm = page.getByRole("form", { name: "Convert to IT student" });
  await expect(adminForm.getByLabel("Batch")).toBeVisible();
  await page.screenshot({ path: "test-results/itc-011-admin-form.png", fullPage: true });
  await adminForm.getByRole("button", { name: "Convert and enrol" }).click();
  await expect(page.getByText(new RegExp(`Converted: CV Lead 3 ${stamp} is enrolled in`))).toBeVisible();
  await expect(page.getByRole("button", { name: `Unlink student from CV Lead 3 ${stamp}` })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
