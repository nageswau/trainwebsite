import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-007 (AC1-AC3, P1, E2, N1): the owner manager moves a university through the §3 stages from its record, the history records every
// change, moving back needs a reason, Lost needs a reason, only the head reopens, and the §4 board counts it in the right column. A
// second manager reads it but cannot move it. Throwaway accounts via the real admin API; a phone-width board has no sideways scroll.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "overseas" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function provision(page: Page, stamp: number) {
  await superAdmin(page);
  const user = async (data: Record<string, unknown>) => (await page.request.post("/api/v1/admin/users", { data })).json();
  const head = await user({ role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc007-h-${stamp}@example.local` });
  const pm = (tag: string) => ({
    role: "partnership_manager", full_name: `E2E Manager ${tag} ${stamp}`, email: `upc007-${tag}-${stamp}@example.local`,
    partnership_profile: { employee_id: `U7${tag}-${stamp}`, reporting_head_user_id: head.id },
  });
  const owner = await user(pm("o"));
  const other = await user(pm("x"));
  await page.request.post("/api/v1/auth/logout");
  for (const u of [head, owner, other]) await activateWithToken(page.request, u.development_welcome_token);
  return { head, owner, other };
}

async function moveTo(page: Page, stage: string, note?: string) {
  await page.getByLabel("Move to").selectOption({ label: stage });
  if (note) await page.getByLabel(/Reason \(required when moving back\)|Note \(optional\)/).fill(note);
  await page.getByRole("button", { name: "Move", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(`Moved to ${stage}.`);
  await expect(page.locator("li[aria-current='step']")).toContainText(stage);
}

test("owner moves through the stages, marks lost; the head reopens; the board counts it", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const name = `E2E Pipeline University ${stamp}`;
  const { head, owner, other } = await provision(page, stamp);

  // Head adds the university and assigns the owner (upc-003 routes).
  await signIn(page, "admin", head.email, "/partnership/head/team");
  const gb = (await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json()).items[0];
  const created = await (await page.request.post("/api/v1/partnership/universities", { data: { name, country_id: gb.id, city: "London" } })).json();
  const id = created.university.id;
  expect((await page.request.post(`/api/v1/partnership/universities/${id}/assign`, { data: { primary_manager_user_id: owner.id } })).status()).toBe(200);

  // Owner: the board from the menu, then the record (P1, AC1).
  await signIn(page, "overseas", owner.email, "/partnership/dashboard");
  await page.getByRole("link", { name: "Partnership Pipeline" }).first().click();
  await page.waitForURL("**/partnership/pipeline");
  await expect(page.getByRole("link", { name: /^Target\s*1$/ })).toBeVisible();
  await page.getByRole("link", { name }).click();
  await page.waitForURL(`**/partnership/universities/${id}`);
  await expect(page.locator("li[aria-current='step']")).toContainText("Target University");
  await expect(page.getByText("No stage changes yet.")).toBeVisible();
  await moveTo(page, "Interested");
  await moveTo(page, "Meeting Scheduled", "Call booked");
  await expect(page.getByText("Kanban column: Meeting Scheduled")).toBeVisible();

  // Moving back needs a reason (PS4).
  await page.getByLabel("Move to").selectOption({ label: "Interested" });
  await expect(page.getByLabel("Reason (required when moving back)")).toHaveAttribute("required", "");
  await moveTo(page, "Interested", "Dean left; restarting");
  const history = page.getByRole("list", { name: "Stage history" });
  await expect(history.getByRole("listitem")).toHaveCount(3);
  await expect(history.getByRole("listitem").first()).toContainText("Meeting Scheduled → Interested");
  await expect(history.getByRole("listitem").first()).toContainText("Note: Dean left; restarting");

  // Lost needs a reason (AC3); a manager cannot reopen.
  await page.getByRole("button", { name: "Mark lost" }).click();
  await page.getByRole("button", { name: "Yes, mark lost" }).click();
  await expect(page.getByLabel("Reason")).toBeFocused(); // the browser refuses an empty required reason
  await page.getByLabel("Reason").fill("Chose another agency");
  await page.getByRole("button", { name: "Yes, mark lost" }).click();
  await expect(page.getByText(/Marked lost on .*Chose another agency/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Reopen" })).toHaveCount(0);
  await expect(page.getByLabel("Move to")).toHaveCount(0);

  // Board: counted under Lost, not in a column (AC2).
  await page.goto("/partnership/pipeline?column=lost");
  await expect(page.getByRole("link", { name })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Interested\s*0$/ })).toBeVisible();

  // Another manager reads but cannot move (N1).
  await signIn(page, "overseas", other.email, "/partnership/dashboard");
  await page.goto(`/partnership/universities/${id}`);
  await expect(page.getByRole("heading", { name: "Partnership stage" })).toBeVisible();
  await expect(page.getByLabel("Move to")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Mark lost|Reopen/ })).toHaveCount(0);

  // Head reopens (E2): back at Interested, history says so.
  await signIn(page, "admin", head.email, "/partnership/head/team");
  await page.getByRole("link", { name: "Partnership Pipeline" }).first().click();
  await page.waitForURL("**/partnership/pipeline");
  await page.goto(`/partnership/universities/${id}`);
  await page.getByRole("button", { name: "Reopen" }).click();
  await page.getByLabel("Reason").fill("They called back");
  await page.getByRole("button", { name: "Yes, reopen" }).click();
  await expect(page.getByRole("status")).toHaveText("Reopened.");
  await expect(page.locator("li[aria-current='step']")).toContainText("Interested");
  await expect(history.getByRole("listitem").first()).toContainText("Reopened at Interested");

  // Phone width: the board has no sideways page scroll.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/partnership/pipeline");
  await expect(page.getByRole("navigation", { name: "Pipeline columns" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
