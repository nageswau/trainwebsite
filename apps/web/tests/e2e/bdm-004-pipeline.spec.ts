import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-004 (AC2, AC3, AC5, AC6, AC8, AC11): a College BDM moves an organization forward, back with a note, marks it lost and revives
// it; the history and the pipeline counts follow; the manager reads but cannot move; nothing overflows at 320 / 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
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

test("BDM pipeline: move, move back with a note, lost, revive, counts, manager read-only", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm004-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm004-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E4-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  });
  const org = (await created.json()).organization;

  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  const stages = page.getByRole("list", { name: "Pipeline stages" });
  await expect(stages.getByRole("listitem").filter({ hasText: "College Prospect" })).toHaveAttribute("aria-current", "step");
  await expect(stages.getByRole("listitem").filter({ hasText: "Placement" })).toContainText("Not tracked");

  // AC2 forward (skipping), keyboard only
  await page.getByLabel("Move to").focus();
  await page.getByLabel("Move to").selectOption("proposal");
  await page.getByRole("button", { name: "Move", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Moved to Proposal." })).toBeVisible();
  const history = page.getByRole("list", { name: "Stage history" });
  await expect(history.getByText("College Prospect → Proposal")).toBeVisible();

  // AC3 back needs a note
  await page.getByLabel("Move to").selectOption("contacted");
  await expect(page.getByLabel("Reason (required when moving back)")).toHaveAttribute("required", "");
  await page.getByLabel("Reason (required when moving back)").fill("Proposal was premature");
  await page.getByRole("button", { name: "Move", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Moved to Contacted." })).toBeVisible();
  await expect(history.getByText("Note: Proposal was premature")).toBeVisible();

  // AC8 lost, then revive
  await page.getByRole("button", { name: "Mark lost" }).click();
  await page.getByLabel("Reason", { exact: true }).fill("No budget this year");
  await page.getByRole("button", { name: "Yes, mark lost" }).click();
  await expect(page.getByText(/Marked lost on .*No budget this year/)).toBeVisible();
  await expect(page.getByLabel("Move to")).toHaveCount(0);
  await page.getByRole("button", { name: "Revive" }).click();
  await page.getByLabel("Reason", { exact: true }).fill("New principal");
  await page.getByRole("button", { name: "Yes, revive" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Revived." })).toBeVisible();
  await noOverflow(page);

  // AC5 my pipeline
  await page.getByRole("link", { name: "Pipeline", exact: true }).first().click();
  await page.waitForURL("**/bdm/pipeline");
  const tiles = page.getByRole("navigation", { name: "Pipeline stages" });
  await expect(tiles.getByRole("link", { name: /Contacted\s*1/ })).toBeVisible();
  await tiles.getByRole("link", { name: /Contacted\s*1/ }).click();
  await expect(page.getByRole("region", { name: "Organizations", exact: true }).getByText(`E2E College ${stamp}`)).toBeVisible();
  await noOverflow(page);

  // AC6 the manager reads the team pipeline and the organization, without move controls
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/pipeline");
  await expect(page.getByRole("navigation", { name: "Pipeline stages" }).getByRole("link", { name: /Contacted\s*1/ })).toBeVisible();
  await page.goto(`/bdm/manager/organizations/${org.id}`);
  await expect(page.getByRole("list", { name: "Pipeline stages" })).toBeVisible();
  await expect(page.getByLabel("Move to")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mark lost" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Stage history" }).getByText("Revived at Contacted")).toBeVisible();
  await noOverflow(page);
});
