import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-022 (AC1-AC4): an Agent organization shows "Not onboarded yet" until Overseas Admin links its agency (bdm-019); once linked, the
// BDM and the manager see the agency's own chain -- Students, Applications, Offers, Visa, Enrolled, Revenue (not tracked) -- and the
// applications by stage, never a student's name. Nothing overflows at 320 / 375 / 768 px. Unique names per run (shared E2E DB).
test.describe.configure({ timeout: 150_000 });

async function signIn(page: Page, portal: "overseas" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function apiLogin(request: APIRequestContext, email: string, password: string) {
  await request.post("/api/v1/auth/logout");
  expect((await request.post("/api/v1/auth/login", { data: { email, password, division: "overseas" } })).status()).toBe(200);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375, 768]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

const chainStep = (page: Page, label: string) =>
  page.getByRole("list", { name: "Agent performance chain" }).getByRole("listitem").filter({ has: page.locator(".pipeline-label", { hasText: new RegExp(`^${label}$`) }) });

test("Agent performance: not onboarded, then the linked agency's own figures with the stage drill-down", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  const studentName = `E2E Perf Student ${stamp}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm022-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E Agent BDM ${stamp}`, email: `bdm022-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "agent", employee_id: `E2E22-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  // The BDM's organization reaches Agreement Signed (bdm-005 M5) and requests onboarding; nothing is linked yet.
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "agent", name: `E2E Perf Lead ${stamp}`, city: "Kochi", contacts: [{ name: "Ravi", role: "owner", email: `ravi22-${stamp}@example.local` }] },
  })).json()).organization;
  expect((await page.request.post(`/api/v1/bdm/organizations/${org.id}/mou`, { data: { status: "signed", signed_on: "2026-10-01" } })).status()).toBe(201);
  expect((await page.request.post(`/api/v1/bdm/organizations/${org.id}/onboarding-request`, { data: {} })).status()).toBe(201);
  await page.goto(`/bdm/organizations/${org.id}`);
  const panel = page.getByRole("region", { name: "Agent performance" });
  await expect(panel).toContainText("Not onboarded yet. Figures appear once Overseas Admin links the agent organization.");

  // Overseas Admin creates and approves an agency (AGN-001, unchanged) and links it to the request (bdm-019).
  await signIn(page, "overseas", "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const agentEmail = `bdm022-a-${stamp}@example.local`;
  const owner = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "agent", division: "overseas", full_name: `E2E Perf Owner ${stamp}`, email: agentEmail, profile: { agency_name: `E2E Perf Globe ${stamp}` } },
  })).json();
  const agency = (await (await page.request.get("/api/v1/overseas-admin/agent-orgs", { params: { q: agentEmail } })).json()).items[0];
  expect((await page.request.post(`/api/v1/overseas-admin/agent-orgs/${agency.id}/approve`)).status()).toBe(200);
  let requestId: string | undefined;
  for (let offset = 0; !requestId; offset += 100) {
    const queue = await (await page.request.get("/api/v1/overseas-admin/bdm-onboarding-requests", { params: { kind: "agent", status: "pending", limit: 100, offset } })).json();
    requestId = queue.items.find((i: { organization: { id: string } }) => i.organization.id === org.id)?.id;
    expect(offset, "the request is in the agent queue").toBeLessThan(queue.total + 100);
  }
  expect((await page.request.post(`/api/v1/overseas-admin/bdm-onboarding-requests/${requestId}/link-agent`, { data: { agent_code: agency.prefix } })).status()).toBe(200);

  // The agency works: one student, two applications -- one still an enquiry, one moved to Offer.
  await activateWithToken(page.request, owner.development_welcome_token);
  await apiLogin(page.request, agentEmail, E2E_PASSWORD);
  const crm = "/api/v1/workflows/overseas/agent/crm";
  const student = (await (await page.request.post(`${crm}/students`, { data: { full_name: studentName } })).json()).student;
  const universities = await (await page.request.get("/api/v1/public/universities")).json();
  const applications = [];
  for (const university of universities.slice(0, 2)) {
    const created = await page.request.post(`${crm}/applications`, { data: { agent_student_id: student.id, university_id: university.id, intake: "September 2027" } });
    expect(created.status(), await created.text()).toBe(201);
    applications.push((await created.json()).application);
  }
  const moved = await page.request.post(`${crm}/applications/${applications[1].id}/status`, { data: { to_status: "offer", expected_status: "enquiry" } });
  expect(moved.status(), await moved.text()).toBe(200);

  // The BDM sees the agency's own figures (AC1-AC3), and the drill-down by stage -- never the student (AC4).
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  await expect(panel).toContainText(`E2E Perf Globe ${stamp} (${agency.prefix})`);
  await expect(chainStep(page, "Students").locator(".pipeline-count")).toHaveText("1");
  await expect(chainStep(page, "Applications").locator(".pipeline-count")).toHaveText("2");
  await expect(chainStep(page, "Offers").locator(".pipeline-count")).toHaveText("1");
  await expect(chainStep(page, "Visa").locator(".pipeline-count")).toHaveText("0");
  await expect(chainStep(page, "Enrolled").locator(".pipeline-count")).toHaveText("0");
  await expect(chainStep(page, "Revenue")).toContainText("Not tracked yet");
  await panel.getByRole("button", { name: "Show applications by stage" }).click();
  const byStage = panel.getByRole("table", { name: "Applications by stage" });
  await expect(byStage.getByRole("row", { name: /^Enquiry/ })).toContainText("1");
  await expect(byStage.getByRole("row", { name: /^Offer/ })).toContainText("1");
  await expect(page.getByRole("main")).not.toContainText(studentName);
  await noOverflow(page);

  // The manager's organization page shows the same panel.
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto(`/bdm/manager/organizations/${org.id}`);
  await expect(chainStep(page, "Applications").locator(".pipeline-count")).toHaveText("2");
});
