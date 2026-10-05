import { expect, test, type Browser, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-010 (AC11, AC12): a College BDM plans Hyderabad → Vijayawada, the manager approves it, the BDM adds expenses and completes
// it; a rejected trip is edited and resubmitted; the pages fit a phone; the form and the reject reason work by keyboard alone.
// Throwaway accounts through the real admin API (the bdm-001 pattern).

type People = { bdmEmail: string; managerEmail: string; stamp: string };

// Each test provisions its own manager and BDM and drives two portals, so the 15 s default is too tight (agn-0xx specs do the same).
test.describe.configure({ timeout: 90_000 });

// Saving a draft and opening a trip are client-side navigations (router.push): no `load` event fires, so wait for the URL commit.
const TRIP_URL = /\/bdm\/travel\/[0-9a-f-]{36}$/;

const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function createPeople(browser: Browser): Promise<People> {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`; // unique across parallel workers and --repeat-each
  const context = await browser.newContext();
  const page = await context.newPage();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm010-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm010-b-${stamp}@example.local`,
      bdm_profile: { bdm_type: "college", employee_id: `E2E10-${stamp}`, territory: "Hyderabad", reporting_manager_user_id: manager.id },
    },
  })).json();
  await activateWithToken(page.request, bdm.development_welcome_token);
  await activateWithToken(page.request, manager.development_welcome_token);
  await context.close();
  return { bdmEmail: bdm.email, managerEmail: manager.email, stamp };
}

async function signIn(browser: Browser, portal: "it" | "admin", email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
  return page;
}

async function createTrip(page: Page, from = "Hyderabad", to = "Vijayawada"): Promise<string> {
  // Under parallel load a fill that lands before hydration is reset by React; wait for the page to settle, then check the dates held.
  await page.goto("/bdm/travel/new", { waitUntil: "networkidle" });
  await page.getByLabel("Travel date").fill(today());
  await page.getByLabel("Return date").fill(today());
  await expect(page.getByLabel("Travel date")).toHaveValue(today());
  await page.getByLabel("From").fill(from);
  await page.getByLabel("To").fill(to);
  await page.getByLabel("Purpose").fill("College visits");
  await page.getByLabel("Mode of travel").selectOption("train");
  await page.getByLabel("Estimated cost (₹)").fill("2500");
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.waitForURL(TRIP_URL, { waitUntil: "commit" });
  return page.url().split("/").pop()!;
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test("AC12: create, submit, approve, add expenses, complete", async ({ browser }) => {
  const people = await createPeople(browser);
  const bdm = await signIn(browser, "it", people.bdmEmail, "/bdm/my-day");
  await bdm.getByRole("link", { name: "Travel" }).click();
  await expect(bdm.getByText("No trips yet")).toBeVisible();
  const id = await createTrip(bdm);
  await expect(bdm.getByText("Approval: Draft").first()).toBeVisible();
  await bdm.getByRole("button", { name: "Submit for approval" }).click();
  await expect(bdm.getByText("Approval: Submitted").first()).toBeVisible();

  const manager = await signIn(browser, "admin", people.managerEmail, "/bdm/manager/dashboard");
  await manager.getByRole("link", { name: "Approvals" }).click();
  const queue = manager.getByRole("region", { name: "Trips waiting for approval" });
  await expect(queue.getByText(`E2E BDM ${people.stamp}`)).toBeVisible();
  await queue.getByRole("link").first().click();
  await manager.getByRole("button", { name: "Approve" }).click();
  await expect(manager.getByText("Approval: Approved").first()).toBeVisible();

  await bdm.goto(`/bdm/travel/${id}`);
  await bdm.getByRole("button", { name: "Add expense" }).click();
  await bdm.getByLabel("Category").selectOption("food");
  await bdm.getByLabel("Amount (₹)").fill("450.50");
  await bdm.getByRole("button", { name: "Save expense" }).click();
  await expect(bdm.getByRole("region", { name: "Expenses", exact: true })).toContainText("₹450.50"); // not "Costs and expenses"
  await bdm.getByRole("button", { name: "Add expense" }).click();
  await bdm.getByLabel("Category").selectOption("stay");
  await bdm.getByLabel("Amount (₹)").fill("1200");
  await bdm.getByRole("button", { name: "Save expense" }).click();
  await expect(bdm.getByRole("group", { name: "Costs" })).toContainText("₹1,650.50");
  await bdm.getByRole("button", { name: "Mark completed" }).click();
  await expect(bdm.getByText("Travel: Completed").first()).toBeVisible();
  await bdm.getByRole("textbox", { name: "Remarks" }).fill("Two MoUs signed"); // the section is also named "Remarks"
  await bdm.getByRole("button", { name: "Save remarks" }).click();
  await expect(bdm.getByRole("status").filter({ hasText: "Remarks saved" })).toBeVisible();
});

test("reject with a reason, then edit and resubmit", async ({ browser }) => {
  const people = await createPeople(browser);
  const bdm = await signIn(browser, "it", people.bdmEmail, "/bdm/my-day");
  const id = await createTrip(bdm, "Hyderabad", "Guntur");
  await bdm.getByRole("button", { name: "Submit for approval" }).click();
  await expect(bdm.getByText("Approval: Submitted").first()).toBeVisible();

  const manager = await signIn(browser, "admin", people.managerEmail, "/bdm/manager/dashboard");
  await manager.goto(`/bdm/manager/trips/${id}`);
  await manager.getByRole("button", { name: "Reject" }).click();
  await manager.getByLabel("Reason for rejecting").fill("Combine with next week's Vijayawada trip");
  await manager.getByRole("button", { name: "Confirm reject" }).click();
  await expect(manager.getByText("Approval: Rejected").first()).toBeVisible();

  await bdm.reload();
  await expect(bdm.getByText("Combine with next week's Vijayawada trip")).toBeVisible();
  await bdm.getByLabel("To", { exact: true }).fill("Vijayawada");
  await bdm.getByRole("button", { name: "Save changes" }).click();
  await expect(bdm.getByRole("status").filter({ hasText: "Trip saved." })).toBeVisible();
  // the heading comes from the server render that router.refresh() fetches after the save
  await expect(bdm.getByRole("heading", { name: "Hyderabad → Vijayawada" })).toBeVisible({ timeout: 15_000 });
  await bdm.getByRole("button", { name: "Submit for approval" }).click();
  await expect(bdm.getByText("Approval: Submitted").first()).toBeVisible();
});

for (const width of [320, 375]) {
  test(`AC11: no horizontal scroll at ${width}px`, async ({ browser }) => {
    const people = await createPeople(browser);
    const bdm = await signIn(browser, "it", people.bdmEmail, "/bdm/my-day");
    const id = await createTrip(bdm);
    await bdm.getByRole("button", { name: "Submit for approval" }).click();
    await expect(bdm.getByText("Approval: Submitted").first()).toBeVisible();
    await bdm.setViewportSize({ width, height: 800 });
    for (const path of ["/bdm/travel", `/bdm/travel/${id}`, "/bdm/travel/new"]) {
      await bdm.goto(path);
      await noHorizontalScroll(bdm);
    }
    const manager = await signIn(browser, "admin", people.managerEmail, "/bdm/manager/dashboard");
    await manager.setViewportSize({ width, height: 800 });
    for (const path of ["/bdm/manager/approvals", `/bdm/manager/trips/${id}`]) {
      await manager.goto(path);
      await noHorizontalScroll(manager);
    }
  });
}

test("AC11: keyboard only — create a trip, and the reject reason keeps focus", async ({ browser }) => {
  const people = await createPeople(browser);
  const bdm = await signIn(browser, "it", people.bdmEmail, "/bdm/my-day");
  await bdm.goto("/bdm/travel/new", { waitUntil: "networkidle" });
  // Date pickers are filled directly (their typed format depends on the browser locale); every other step is Tab and typing.
  await bdm.getByLabel("Travel date").fill(today());
  await bdm.getByLabel("Return date").fill(today());
  await expect(bdm.getByLabel("Travel date")).toHaveValue(today());
  await bdm.getByLabel("From").focus(); // a date input holds several Tab stops (day, month, year, picker)
  await bdm.keyboard.type("Hyderabad");
  await bdm.keyboard.press("Tab");
  await bdm.keyboard.type("Vijayawada");
  await bdm.keyboard.press("Tab"); // mode keeps its default
  await bdm.keyboard.press("Tab");
  await bdm.keyboard.type("2500");
  await bdm.keyboard.press("Tab");
  await bdm.keyboard.type("Keyboard-only trip");
  await bdm.getByRole("button", { name: "Save draft" }).focus();
  await bdm.keyboard.press("Enter");
  await bdm.waitForURL(TRIP_URL, { waitUntil: "commit" });
  const id = bdm.url().split("/").pop()!;
  await bdm.getByRole("button", { name: "Submit for approval" }).focus();
  await bdm.keyboard.press("Enter");
  await expect(bdm.getByText("Approval: Submitted").first()).toBeVisible();

  const manager = await signIn(browser, "admin", people.managerEmail, "/bdm/manager/dashboard");
  await manager.goto(`/bdm/manager/trips/${id}`);
  await manager.getByRole("button", { name: "Reject" }).focus();
  await manager.keyboard.press("Enter");
  await expect(manager.getByLabel("Reason for rejecting")).toBeFocused();
  await manager.keyboard.press("Escape");
  await expect(manager.getByRole("button", { name: "Reject" })).toBeFocused();
});
