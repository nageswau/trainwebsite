import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-008 (AC1-AC3, D4, D5): the lead workspace. Assigning a lead to a telecaller arrives with tel-007 (no HTTP path yet), so the
// worked journey is the manager's: a fresh website lead sits in the IT unassigned queue of a manager whose telecaller is in IT (T23).
// The telecaller's side checks the empty My Leads and that another lead's id reads as not found (AC2).
test.describe.configure({ timeout: 120_000 });

async function accounts(page: Page, stamp: number) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Lead Manager ${stamp}`, email: `tel008-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Lead Telecaller ${stamp}`, email: `tel008-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `LW-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a manager opens a queue lead, sets its priority and stage, edits it, and finds it by priority", async ({ page }) => {
  const stamp = Date.now();
  const { manager } = await accounts(page, stamp);
  const name = `Workspace Lead ${stamp}`;
  const mobile = `9${String(stamp).slice(-9)}`; // tel-005 (T12): a known mobile would attach to its existing lead
  const created = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name, email: `tel008-${stamp}@example.com`, phone: `${mobile.slice(0, 5)} ${mobile.slice(5)}`, subject: "Cyber Security", message: "Call me after 6pm." },
  });
  expect(created.status()).toBe(201);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.getByRole("link", { name: "Leads", exact: true }).first().click();
  await page.waitForURL("**/telecaller/manager/leads");
  await page.getByLabel("Search leads").fill(name);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(/q=Workspace/);
  await page.getByRole("link", { name }).click();
  await page.waitForURL(/\/telecaller\/manager\/leads\/[0-9a-f-]{36}$/);

  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Call me after 6pm.")).toBeVisible();
  await expect(page.getByRole("link", { name: `Call ${name}` })).toHaveAttribute("href", `tel:${mobile}`);
  await expect(page.getByText("No activity yet.")).toBeVisible();
  await expect(page.getByText("Set the lead's product interest to see its call script.")).toBeVisible(); // a website lead has no product

  await page.getByRole("group", { name: "Priority" }).getByLabel(/Hot/).check();
  await page.getByRole("button", { name: "Save priority" }).click();
  await expect(page.getByText("Priority updated.")).toBeVisible();
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity).toContainText("Priority: Warm → Hot");

  await page.getByRole("button", { name: `Change stage for ${name}` }).click();
  await page.getByLabel(`New stage for ${name}`).selectOption("qualified");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await expect(activity.getByRole("listitem").first()).toContainText("Stage: New Lead → Qualified");

  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("City").fill("Hyderabad");
  await page.getByLabel("Email").fill("not-an-email");
  await page.getByRole("button", { name: "Save details" }).click();
  // Next's route announcer is also role=alert, so narrow to the form's message
  await expect(page.getByRole("alert").filter({ hasText: "Enter a valid email address" })).toBeVisible();
  await page.getByLabel("Email").fill(`tel008-${stamp}@example.com`);
  await page.getByLabel("Product interest").selectOption({ label: "Cyber Security" });
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText("Details saved.")).toBeVisible();
  // tel-012 C2: the product's active call script (tel-012 seeds one for Cyber Security; a manager may have edited its steps)
  await expect(page.getByRole("list", { name: "Call script steps" }).getByRole("listitem").first()).toBeVisible();

  await page.reload(); // stored, not just shown
  await expect(page.getByText("Hyderabad")).toBeVisible();
  await expect(page.getByText(/Stage: Qualified · Priority: Hot/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Lead activity" }).getByRole("listitem")).toHaveCount(2);
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page), `no side scroll at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.goto(`/telecaller/manager/leads?priority=hot&q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await page.getByLabel("Priority").selectOption("cold");
  await expect(page.getByText("No leads match these filters.")).toBeVisible();
  // the one expected error: the browser logs the 422 of the invalid-email save
  expect(consoleErrors.filter((text) => !text.includes("422"))).toEqual([]);
});

test("a telecaller's My Leads starts empty and another lead reads as not found", async ({ page }) => {
  const stamp = Date.now();
  const { caller } = await accounts(page, stamp);
  const created = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: `Not Mine ${stamp}`, email: `tel008-x-${stamp}@example.com`, subject: "Java", message: "Please call me." },
  });
  const { id } = await created.json();

  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await page.getByRole("link", { name: "My Leads" }).first().click();
  await page.waitForURL("**/telecaller/leads");
  await expect(page.getByText("No leads are assigned to you yet.")).toBeVisible();
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  await page.goto(`/telecaller/leads/${id}`);
  await expect(page.getByRole("heading", { name: "Lead not found" })).toBeVisible();
  expect((await page.request.get(`/api/v1/telecaller/leads/${id}`)).status()).toBe(404);
  expect((await page.request.patch(`/api/v1/telecaller/leads/${id}`, { data: { priority: "hot" } })).status()).toBe(404);
});
