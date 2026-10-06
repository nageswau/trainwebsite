import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-021 (AC1-AC4, B3): a College organization's Business section. Two leads, one linked to a student with one paid and one pending
// fee: the assigned BDM and the manager see the funnel and ₹15,000.00 of training fees; another College BDM sees the funnel but not
// the revenue; internship is labelled, never a 0; nothing overflows at 320 / 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

function stage(page: Page, label: string) {
  return page.getByRole("list", { name: "Student funnel" }).getByRole("listitem").filter({ has: page.locator(".pipeline-label", { hasText: new RegExp(`^${label}$`) }) });
}

test("College business: funnel and revenue by role", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm021-m-${stamp}@example.com` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm021-b-${stamp}@example.com`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E21-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  const peer = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E Peer ${stamp}`, email: `bdm021-p-${stamp}@example.com`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E21P-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  const student = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "it_student", division: "it", full_name: `E2E Student ${stamp}`, email: `bdm021-s-${stamp}@example.com` },
  })).json();
  for (const account of [manager, bdm, peer, student]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  })).json()).organization;
  const leads = [];
  for (const name of ["Asha Nair", "Ravi Menon"]) {
    const response = await page.request.post(`/api/v1/bdm/organizations/${org.id}/leads`, {
      data: { name, email: `${name.split(" ")[0].toLowerCase()}-${stamp}@example.com`, interest: "Python" },
    });
    leads.push(await response.json());
  }

  // Empty funnel first: the section explains itself.
  const empty = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Empty ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  })).json()).organization;
  await page.goto(`/bdm/organizations/${empty.id}`);
  await expect(page.getByText("No leads yet. The funnel fills in as leads are added and linked to student accounts.")).toBeVisible();

  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  expect((await page.request.post(`/api/v1/admin/leads/${leads[0].id}/conversion`, { data: { student_email: student.email } })).ok()).toBe(true);
  for (const [amount, status] of [["15000", "paid"], ["5000", "pending"]]) {
    expect((await page.request.post("/api/v1/admin/payments", { data: { user_id: student.id, amount, status, reference_type: "enrollment" } })).ok()).toBe(true);
  }

  // AC1, AC2, AC4: the assigned BDM.
  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  const section = page.getByRole("region", { name: "Business" });
  await expect(section).toBeVisible();
  await expect(stage(page, "Leads")).toContainText("2");
  await expect(stage(page, "Registrations")).toContainText("1");
  await expect(stage(page, "Training")).toContainText("0");
  await expect(stage(page, "Internship")).toContainText("Not tracked yet");
  const revenue = page.getByRole("region", { name: "Revenue (INR)" });
  await expect(revenue).toContainText("₹15,000.00");
  await expect(revenue.getByText("Not tracked yet")).toHaveCount(3);
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });

  // B3: another College BDM reads the funnel but not the revenue.
  await signIn(page, "it", peer.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  await expect(stage(page, "Registrations")).toContainText("1");
  await expect(page.getByRole("region", { name: "Revenue (INR)" })).toContainText("Revenue is visible to the organization's assigned BDM and their manager.");
  await expect(page.getByText("₹15,000.00")).toHaveCount(0);

  // The manager sees the revenue on the manager profile.
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto(`/bdm/manager/organizations/${org.id}`);
  await expect(page.getByRole("region", { name: "Revenue (INR)" })).toContainText("₹15,000.00");
});
