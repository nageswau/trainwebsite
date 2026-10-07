import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-019 (AC1-AC3): an Agent organization at Agreement Signed requests onboarding; Overseas Admin links an existing Agent Organization
// by its code from the Agents page; the BDM then sees the live steps -- Agent Onboarding and Master Login Created, then Active Agent once
// the agency is approved -- and never an agency name list. Nothing overflows at 320 / 375 / 768 px.
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

const step = (page: Page, label: string) => page.getByRole("list", { name: "Pipeline stages" }).getByRole("listitem").filter({ hasText: label });

test("Agent handover: request at Agreement Signed, admin links by code, live steps follow the agency", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm019-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E Agent BDM ${stamp}`, email: `bdm019-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "agent", employee_id: `E2E19-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  // The BDM's organization reaches Agreement Signed through a Signed MoU (bdm-005 M5), then requests onboarding in the UI.
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "agent", name: `E2E Agency Lead ${stamp}`, city: "Kochi", contacts: [{ name: "Ravi", role: "owner", email: `ravi-${stamp}@example.local` }] },
  })).json()).organization;
  expect((await page.request.post(`/api/v1/bdm/organizations/${org.id}/mou`, { data: { status: "signed", signed_on: "2026-10-01" } })).status()).toBe(201);
  await page.goto(`/bdm/organizations/${org.id}`);
  const card = page.getByRole("region", { name: "Agent onboarding" });
  await expect(card).toContainText("Ready to hand over");
  await card.getByRole("button", { name: "Request onboarding" }).click();
  await card.getByLabel("Note for Overseas Admin (optional)").fill("Signed last week");
  await card.getByRole("button", { name: "Send request" }).click();
  await expect(card).toContainText("Waiting for Overseas Admin to link the agent organization.");
  await expect(step(page, "Agent Onboarding")).toContainText("Current");

  // Overseas Admin registers the agency (AGN-001 D11: a pending organization with Master M001) and links it from the Agents page.
  await signIn(page, "overseas", "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const agentEmail = `bdm019-a-${stamp}@example.local`;
  expect((await page.request.post("/api/v1/admin/users", {
    data: { role: "agent", division: "overseas", full_name: `E2E Agency Owner ${stamp}`, email: agentEmail, profile: { agency_name: `E2E Globe ${stamp}` } },
  })).status()).toBe(201);
  const agency = (await (await page.request.get("/api/v1/overseas-admin/agent-orgs", { params: { q: agentEmail } })).json()).items[0];
  await page.goto("/overseas/admin/agents");
  const queue = page.getByRole("region", { name: "Agent onboarding requests" });
  const entry = queue.getByRole("listitem").filter({ hasText: org.code });
  await expect(entry).toContainText("Signed last week");
  await expect(entry.getByRole("button", { name: "Use for new school" })).toHaveCount(0);
  await entry.getByRole("button", { name: "Link agent organization" }).click();
  await entry.getByLabel("Agent code").fill(agency.prefix);
  await entry.getByRole("button", { name: "Link agent" }).click();
  await expect(queue.getByRole("status")).toContainText(`${org.code} is now linked to E2E Globe ${stamp} (${agency.prefix}).`);
  await expect(entry).toHaveCount(0);

  // The BDM sees the link and the live steps; the agency is still pending approval.
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  await expect(card).toContainText(`Linked to E2E Globe ${stamp} (code ${agency.prefix}). Status: Pending approval.`);
  await expect(card).toContainText("Master login: Created · Staff logins: 0");
  await expect(step(page, "Agent Onboarding")).toContainText("Done");
  await expect(step(page, "Master Login Created")).toContainText("Done");
  await expect(step(page, "Staff Logins Created")).toContainText("Current");
  await expect(page.getByText("Agent status:")).toContainText("Onboarding");
  await expect(page.getByRole("main")).not.toContainText(`E2E Agency Owner ${stamp}`); // aggregates only (AC4)

  // Overseas Admin approves the agency (AGN-001, unchanged): Active Agent follows live.
  await signIn(page, "overseas", "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  expect((await page.request.post(`/api/v1/overseas-admin/agent-orgs/${agency.id}/approve`)).status()).toBe(200);
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  await expect(card).toContainText("Status: Active.");
  await expect(step(page, "Active Agent")).toContainText("Done");
  await expect(step(page, "Students")).toContainText("0Upcoming");
  await expect(page.getByText("Agent status:")).toContainText("Active");
  await noOverflow(page);
});
