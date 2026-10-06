import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-018 (AC1, AC2, AC4): a School BDM with a Signed MoU requests onboarding; Overseas Admin uses the request to create the School
// (prefilled, linked in the same step); the organization then names the School and its pipeline shows School Onboarding done. Nothing
// overflows at 320 / 375 px.
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
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("School handover: request, create from the request, linked organization with live stages", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm018-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E School BDM ${stamp}`, email: `bdm018-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "school", employee_id: `E2E18-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const name = `E2E School ${stamp}`;
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "school", name, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal", email: `rao-${stamp}@example.local` }] },
  })).json()).organization;
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  const card = page.getByRole("region", { name: "School onboarding" });
  await expect(card).toContainText("Available once the MoU is Signed or Active.");
  expect((await page.request.post(`/api/v1/bdm/organizations/${org.id}/mou`, { data: { status: "signed", signed_on: "2026-10-01", reference: `MOU-${stamp}` } })).status()).toBe(201);
  await page.reload();
  await page.waitForLoadState("networkidle");

  // AC1: the request, keyboard only
  await card.getByRole("button", { name: "Request onboarding" }).focus();
  await page.keyboard.press("Enter");
  await card.getByLabel("Note for Overseas Admin (optional)").fill("Ready from June");
  await card.getByRole("button", { name: "Send request" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Onboarding requested." })).toBeVisible();
  await expect(card).toContainText("Waiting for Overseas Admin");
  const stages = page.getByRole("list", { name: "Pipeline stages" });
  await expect(stages.getByRole("listitem").filter({ hasText: "School Onboarding" })).toHaveAttribute("aria-current", "step");
  await noOverflow(page);

  // AC2: Overseas Admin creates the School from the request; the form is prefilled and the link is made in the same step
  await signIn(page, "overseas", "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  const queue = page.getByRole("region", { name: "School onboarding requests" });
  const entry = queue.getByRole("listitem").filter({ hasText: org.code });
  const rows = queue.getByRole("list", { name: "Onboarding requests" }).getByRole("listitem");
  await expect(rows.first()).toBeVisible();
  // Oldest first: on a shared database earlier runs' requests come before this one, so page on until it shows.
  const more = queue.getByRole("button", { name: "Show more" });
  while (!(await entry.isVisible()) && (await more.isVisible())) {
    const shown = await rows.count();
    await more.click();
    await expect.poll(() => rows.count()).toBeGreaterThan(shown);
  }
  await expect(entry).toContainText("Ready from June");
  await entry.getByRole("button", { name: "Use for new school" }).click();
  await expect(page.getByLabel("School name")).toHaveValue(name);
  await expect(page.getByLabel("Coordinator email")).toHaveValue(`rao-${stamp}@example.local`);
  await expect(page.getByLabel("Agreement / MoU reference")).toHaveValue(`MOU-${stamp}`);
  await page.getByRole("button", { name: "Create school + seed Coordinator" }).click();
  await expect(page.getByText(new RegExp(`School created\\..*Linked to ${org.code}`))).toBeVisible();
  await expect(queue.getByRole("listitem").filter({ hasText: org.code })).toHaveCount(0);
  await noOverflow(page);

  // AC4: the BDM sees the School and the live stage
  await signIn(page, "overseas", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  await expect(card).toContainText(`Onboarded as ${name}`);
  await expect(stages.getByRole("listitem").filter({ hasText: "School Onboarding" })).toContainText("Done");
  await expect(stages.getByRole("listitem").filter({ hasText: "Teachers / Parents / Students Created" })).toHaveAttribute("aria-current", "step");
});
