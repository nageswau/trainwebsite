import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-020 (AC1-AC3, P1): moving a university to Proposal Sent creates "Follow up on proposal" (AC1); the university page shows §20's
// Next / Last Action (P1); the manager adds a follow-up due today, sees it in the Due today band (AC2), completes it, and it is never
// shown as overdue (AC3); rescheduling moves an item between bands; the head reads the team's items; the page fits a phone. Throwaway
// accounts via the real admin API.

const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc020-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc020-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U20-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Tasks University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, university };
}

test("auto follow-up on Proposal Sent, bands, complete, reschedule and the head's team view", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, manager, university } = await setUp(page, stamp);

  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.goto(`/partnership/universities/${university.id}`);
  const section = page.getByRole("region", { name: "Follow-ups & tasks" });
  await expect(section.getByText("No follow-up planned")).toBeVisible();
  await expect(section.getByText("No open follow-ups or tasks.")).toBeVisible();

  // AC1 + P1: the stage move creates the follow-up, and the university shows Last / Next Action.
  await page.getByLabel("Move to").selectOption("proposal_sent");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(section.getByText("Moved to Proposal Sent")).toBeVisible();
  await expect(section.getByText("Follow up on proposal").first()).toBeVisible();
  await expect(section.getByText("High", { exact: true })).toBeVisible();
  await expect(section.getByText("Auto: stage change")).toBeVisible();

  // Add a follow-up due today from the university page.
  await section.getByRole("button", { name: "Add follow-up or task" }).click();
  await section.getByRole("button", { name: "Add" }).click();
  await expect(section.getByText("Title is required")).toBeVisible();
  await section.getByLabel("Title (required)").fill("Follow-up call");
  await section.getByLabel("Due date (IST, required)").fill(inDays(0));
  await section.getByRole("button", { name: "Add" }).click();
  await expect(section.getByText("Added.")).toBeVisible();
  await expect(section.getByLabel("Open follow-ups and tasks").getByText("Follow-up call")).toBeVisible();

  // AC2: the Follow-ups & Tasks page, from the menu: the Due today band holds it; the auto follow-up is Upcoming (+7 days).
  await page.getByRole("link", { name: "Follow-ups & Tasks" }).first().click();
  await expect(page.getByRole("heading", { name: "Follow-ups & tasks" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Due today (1)" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("button", { name: "Upcoming (1)" })).toBeVisible();
  const item = page.getByRole("listitem").filter({ hasText: "Follow-up call" });
  await expect(item.getByRole("link", { name: university.name })).toBeVisible();

  // AC3: done is never overdue; it moves to Done.
  await item.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Marked done.")).toBeVisible();
  await expect(page.getByText("Nothing due today.")).toBeVisible();
  await page.getByRole("button", { name: "Done (1)" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Follow-up call" }).getByText("Done", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Overdue (0)" }).click();
  await expect(page.getByText("Nothing overdue.")).toBeVisible();

  // Reschedule the auto follow-up to tomorrow: it moves to Due tomorrow.
  await page.getByRole("button", { name: "Upcoming (1)" }).click();
  const auto = page.getByRole("listitem").filter({ hasText: "Follow up on proposal" });
  await auto.getByRole("button", { name: "Reschedule" }).click();
  await auto.getByLabel("New due date (IST)").fill(inDays(1));
  await auto.getByRole("button", { name: "Save date" }).click();
  await expect(page.getByText("Rescheduled.")).toBeVisible();
  await page.getByRole("button", { name: "Due tomorrow (1)" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Follow up on proposal" })).toBeVisible();

  // The university's Last Action is now the completed call (later than the stage move).
  await page.goto(`/partnership/universities/${university.id}`);
  await expect(page.getByRole("region", { name: "Follow-ups & tasks" }).getByText("Follow-up call")).toBeVisible();

  // The head sees the team's items by default and may act on them (TK11).
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.goto("/partnership/tasks?band=tomorrow");
  await expect(page.getByLabel("Show")).toHaveValue("team");
  const teamItem = page.getByRole("listitem").filter({ hasText: "Follow up on proposal" });
  await expect(teamItem.getByText(`Owner: E2E Manager ${stamp}`)).toBeVisible();
  await expect(teamItem.getByRole("button", { name: "Done" })).toBeVisible();
  await page.getByLabel("Show").selectOption("me");
  await expect(page.getByText("Nothing due tomorrow.")).toBeVisible();

  // The super admin reads every item from its own menu (TK8), without the add or action buttons.
  await page.request.post("/api/v1/auth/logout");
  await superAdmin(page);
  await page.getByRole("link", { name: "Partnership Follow-ups & Tasks" }).click();
  await page.getByRole("button", { name: /^Due tomorrow/ }).click();
  await expect(page.getByRole("listitem").filter({ hasText: university.name })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add follow-up or task" })).toHaveCount(0);

  // Phone width: no horizontal scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/partnership/tasks?band=tomorrow");
  await expect(page.getByRole("listitem").filter({ hasText: university.name })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
