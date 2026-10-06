import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-020 (AC1-AC3): a School organization shows "Not onboarded yet" until Overseas Admin links a School; then the School activity
// panel shows the School's own student total and Completed / Pending per metric, with Student Profile Completion "Not tracked" -- on
// the BDM's page and on the manager's. Nothing overflows at 320 / 375 / 768 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "overseas" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375, 768]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("School activity: not onboarded yet, then the linked School's counts on the BDM and manager pages", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm020-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E School BDM ${stamp}`, email: `bdm020-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "school", employee_id: `E2E20-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const name = `E2E Activity School ${stamp}`;
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "school", name, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal", email: `rao-${stamp}@example.local` }] },
  })).json()).organization;
  await page.goto(`/bdm/organizations/${org.id}`);
  const panel = page.getByRole("region", { name: "School activity" });
  await expect(panel).toContainText("Not onboarded yet. Counts appear once Overseas Admin links the School.");
  await expect(panel.getByRole("table")).toHaveCount(0);

  // Handover through the API (bdm-018's own UI is covered by its spec): MoU Signed, request, Overseas Admin creates the School.
  expect((await page.request.post(`/api/v1/bdm/organizations/${org.id}/mou`, { data: { status: "signed", signed_on: "2026-10-01" } })).status()).toBe(201);
  expect((await page.request.post(`/api/v1/bdm/organizations/${org.id}/onboarding-request`, { data: {} })).status()).toBe(201);
  await signIn(page, "overseas", "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const queue = await (await page.request.get("/api/v1/overseas-admin/bdm-onboarding-requests", { params: { status: "pending", limit: 100, offset: 0 } })).json();
  let item = queue.items.find((i: { organization: { id: string } }) => i.organization.id === org.id);
  for (let offset = 100; !item && offset < queue.total; offset += 100) {
    const next = await (await page.request.get("/api/v1/overseas-admin/bdm-onboarding-requests", { params: { status: "pending", limit: 100, offset } })).json();
    item = next.items.find((i: { organization: { id: string } }) => i.organization.id === org.id);
  }
  const coordinatorEmail = `bdm020-c-${stamp}@example.local`;
  const created = await page.request.post("/api/v1/overseas-admin/schools", {
    data: { name, coordinator_full_name: "E2E Coordinator", coordinator_email: coordinatorEmail, bdm_onboarding_request_id: item.id },
  });
  expect(created.status()).toBe(201);
  const school = await created.json();
  await activateWithToken(page.request, school.development_welcome_token);
  await signIn(page, "overseas", coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  for (const student of ["Ravi Kumar", "Meera Nair"]) expect((await page.request.post("/api/v1/school/students", { data: { full_name: student } })).status()).toBe(201);

  // AC1-AC3 on the BDM's page
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  await expect(panel).toContainText(`${name} (School ID ${school.school_code}) · 2 students`);
  const careerRow = panel.getByRole("row", { name: /Career Guidance/ });
  await expect(careerRow.getByRole("cell")).toHaveText(["0", "2"]);
  for (const label of ["Psychometric Test", "Foreign Language", "English Testing", "University Guidance"]) await expect(panel.getByRole("row", { name: new RegExp(label) })).toBeVisible();
  await expect(panel.getByRole("row", { name: /Student Profile Completion/ })).toContainText("Not tracked");
  await expect(panel).not.toContainText("Ravi");
  await noOverflow(page);
  for (const width of [320, 375]) {  // QA20-01: three short columns fit a phone; the counts are never scrolled out of sight
    await page.setViewportSize({ width, height: 800 });
    const box = await panel.locator(".table-scroll").evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    expect(box.scroll, `table scrolls at ${width}px`).toBeLessThanOrEqual(box.client);
    await careerRow.scrollIntoViewIfNeeded();
    await expect(careerRow.getByRole("cell").last()).toBeInViewport({ ratio: 1 });
  }
  await page.setViewportSize({ width: 1280, height: 800 });

  // The manager's page shows the same panel
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto(`/bdm/manager/organizations/${org.id}`);
  await expect(panel).toContainText("2 students");
  await expect(panel.getByRole("row", { name: /Career Guidance/ }).getByRole("cell")).toHaveText(["0", "2"]);
});
