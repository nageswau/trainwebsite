import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-013 (DEC-SCOPE-163; AC: the §12 example sequence in order with actor and summary): the owning manager logs a call on the page and
// the Communication history shows it without a reload (TL10); a meeting and two stage moves recorded through the API read newest first
// with the actor; the section fits a phone; overseas_admin reads the master but has no history section (TL2). Throwaway accounts.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const head = await post(page, "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc013-h-${stamp}@example.local` });
  const owner = await post(page, "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc013-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U13-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post(page, "/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E OA ${stamp}`, email: `upc013-a-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post(page, "/api/v1/partnership/universities", { name: `E2E Timeline University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(page, `/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: owner.id });
  await post(page, `/api/v1/partnership/universities/${university.id}/contacts`, { name: "Priya Raman", phone: "+44 20 7000 0000" });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, owner, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { owner, admin, university };
}

async function move(page: Page, universityId: string, to: string) {
  const { university } = await (await page.request.get(`/api/v1/partnership/universities/${universityId}`)).json();
  await post(page, `/api/v1/partnership/universities/${universityId}/stage`, { from_stage: university.pipeline.stage, to_stage: to, note: null });
}

test("upc-013: the communication history reads newest first, with the actor, for the partnership roles only", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { owner, admin, university } = await setUp(page, stamp);
  const uniPath = `/partnership/universities/${university.id}`;

  await signIn(page, "/overseas/login", owner.email);
  await page.goto(uniPath);
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Communication history" }) });
  await expect(section.getByText("No activity yet.")).toBeVisible();

  // a call logged on the page shows in the history without a reload (TL10)
  await page.getByRole("button", { name: "Log call" }).click();
  const form = page.getByRole("form", { name: "Log call" });
  await form.getByLabel("Contact (required)").selectOption({ label: "Priya Raman" });
  await form.getByLabel("Outcome (required)").selectOption("connected");
  await form.getByLabel("Notes").fill("Discussed the proposal.");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(page.getByText("Call logged.")).toBeVisible();
  const history = section.getByRole("list", { name: "Communication history" });
  await expect(history.getByRole("listitem").first()).toContainText("Outgoing call: Connected");

  // the §12 sequence: call → meeting scheduled → proposal sent → commercial discussion, newest first
  const startsAt = new Date(Date.now() + 3 * 86_400_000).toISOString();
  const { meeting } = await post(page, "/api/v1/partnership/meetings", { university_id: university.id, meeting_type: "introduction", starts_at: startsAt, mode: "online", meeting_url: "https://meet.example.com/x" });
  await move(page, university.id, "proposal_sent");
  await move(page, university.id, "commercial_discussion");
  await page.reload();
  const titles = await history.locator(".jtl-title").allInnerTexts();
  const at = (pattern: RegExp) => titles.findIndex((t) => pattern.test(t));
  const order = [/→ Commercial Discussion/, /→ Proposal Sent/, /^Meeting scheduled: Introduction/, /^Outgoing call: Connected/].map(at);
  expect(order.every((i) => i >= 0), titles.join(" | ")).toBe(true);
  expect([...order].sort((a, b) => a - b)).toEqual(order);
  const scheduled = history.getByRole("listitem").filter({ hasText: /^Meeting scheduled: Introduction/ });
  await expect(scheduled).toContainText(meeting.code);
  await expect(scheduled).toContainText(`E2E Manager ${stamp}`);
  await expect(history.getByRole("listitem").filter({ hasText: "Outgoing call" })).toContainText("With Priya Raman");

  await page.setViewportSize({ width: 390, height: 844 });
  await section.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // overseas_admin reads the master, never the history (TL2)
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(uniPath);
  await expect(page.getByRole("heading", { name: university.name })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Communication history" })).toHaveCount(0);
  expect((await page.request.get(`/api/v1/partnership/universities/${university.id}/timeline`)).status()).toBe(403);
});
