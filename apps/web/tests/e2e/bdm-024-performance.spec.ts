import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-024 (AC1-AC5): a manager's performance table by BDM type for this month; a number drills down type -> BDM -> organization page,
// and the counts agree at each level; untracked revenue is labelled; the period filter changes the figures; the master view lists the
// organization; a BDM is refused; super_admin narrows to the team; no sideways page scroll on a phone.

async function superAdmin(page: Page) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const ROWS = ["BDMs", "Meetings", "Travel Trips", "New Organizations", "MoUs", "Leads", "Students", "Revenue"];

test("performance by type: table, drill-down that agrees, period filter, master view, roles, phone width", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Perf Manager ${stamp}`, email: `bdm024-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E Perf BDM ${stamp}`, email: `bdm024-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E24-${stamp}`, territory: "Kochi", reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  // The BDM adds a college and two student leads this month: New Organizations 1, Leads 2 in the College column.
  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const college = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Perf College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;
  for (const n of [1, 2]) {
    const lead = await page.request.post(`/api/v1/bdm/organizations/${college.id}/leads`, {
      data: { name: `Student ${n}`, email: `bdm024-s${n}-${stamp}@example.local`, interest: "Python" },
    });
    expect(lead.status(), await lead.text()).toBe(201);
  }

  // Negative scenario: a BDM is refused.
  await page.goto("/bdm/manager/performance");
  await expect(page.getByText("BDM manager role required")).toBeVisible();

  // AC1 / AC3: the source's rows and columns; untracked revenue is labelled.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.getByRole("link", { name: "Performance", exact: true }).click();
  await page.waitForURL("**/bdm/manager/performance");
  const table = page.getByRole("region", { name: "Performance by BDM type" }).getByRole("table");
  await expect(table.locator("tbody th")).toHaveText(ROWS);
  await expect(table.locator("thead th")).toHaveText(["KPI", "Agent BDM", "School BDM", "College BDM"]);
  const revenue = table.locator("tbody tr", { has: page.getByRole("rowheader", { name: "Revenue" }) });
  await expect(revenue.getByText("Not tracked")).toHaveCount(2);
  await expect(revenue.getByRole("link")).toHaveText("₹0.00");

  // AC2: College leads 2 -> the College BDMs (Asha's row 2, Total 2) -> the BDM's organizations (2) -> the organization page.
  await page.getByRole("link", { name: "College BDM Leads: 2. View the BDMs" }).click();
  await page.waitForURL("**/bdm/manager/performance/college**");
  await expect(page.getByRole("heading", { name: "College BDMs" })).toBeVisible();
  await expect(page.getByRole("link", { name: `E2E Perf BDM ${stamp} Leads: 2` })).toBeVisible();
  await expect(page.locator("tfoot td").nth(4)).toHaveText("2");
  await page.getByRole("link", { name: `E2E Perf BDM ${stamp} Leads: 2` }).click();
  await page.waitForURL(`**/bdm/manager/performance/bdms/${bdm.id}**`);
  await expect(page.getByRole("link", { name: `${college.name} Leads: 2` })).toBeVisible();
  await expect(page.getByRole("link", { name: `${college.name} New Organizations: 1` })).toBeVisible();
  await expect(page.getByText("No trips in this period.")).toBeVisible();
  await page.getByRole("link", { name: college.name, exact: true }).click();
  await page.waitForURL(`**/bdm/manager/organizations/${college.id}`);
  await expect(page.getByText(college.name).first()).toBeVisible();

  // AC4: a past month has none of it.
  await page.goto("/bdm/manager/performance?from=2025-03-01&to=2025-03-31");
  await expect(page.getByRole("link", { name: "College BDM Leads: 0. View the BDMs" })).toBeVisible();
  await page.goto("/bdm/manager/performance?from=2025-03-31&to=2025-03-01");
  // The card, not Next's route announcer (also role=alert).
  await expect(page.locator(".card[role=alert]")).toContainText("The period must start on or before its end");

  // Master view: College BDM -> the BDM -> the organization with its value chain.
  await page.goto("/bdm/manager/hierarchy");
  const collegeBranch = page.getByRole("region", { name: "College BDM" });
  await expect(collegeBranch.getByText("Students → Training → Internship → Placement → Revenue")).toBeVisible();
  await collegeBranch.locator("summary", { hasText: `E2E Perf BDM ${stamp}` }).click();
  await expect(collegeBranch.getByRole("link", { name: college.name })).toHaveAttribute("href", `/bdm/manager/organizations/${college.id}`);

  // AC5: no sideways page scroll on a phone or a tablet (the tables scroll inside their box).
  for (const path of ["/bdm/manager/performance", `/bdm/manager/performance/college`, `/bdm/manager/performance/bdms/${bdm.id}`, "/bdm/manager/hierarchy"]) {
    for (const width of [375, 768]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(path);
      await expect(page.locator(".portal-content h2")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${path} @ ${width}`).toBe(true);
    }
  }
  await page.setViewportSize({ width: 1280, height: 800 });

  // super_admin narrows to this manager's team from the admin sidebar.
  await superAdmin(page);
  await page.getByRole("link", { name: "BDM Performance" }).click();
  await page.waitForURL("**/bdm/manager/performance");
  await page.goto(`/bdm/manager/performance?manager=${manager.id}`);
  await expect(page.getByRole("heading", { name: `E2E Perf Manager ${stamp}'s team` })).toBeVisible();
  await expect(page.getByRole("link", { name: "College BDM BDMs: 1. View the BDMs" })).toBeVisible();
});
