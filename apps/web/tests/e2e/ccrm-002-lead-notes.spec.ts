import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-002 (DEC-SCOPE-242): an IT telecaller hands a lead to a counselor and still adds a note (N1); the counselor adds one too and sees
// both in Notes (full text) and in the Activity timeline with author; another counselor's lead is 404. Throwaway accounts; phone width
// has no sideways scroll.
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("telecaller and counselor keep notes on a handed-over lead", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E NT Manager ${stamp}`, email: `ccrm002-m-${stamp}@example.local` });
  const callerName = `E2E NT Telecaller ${stamp}`;
  const caller = await post({
    role: "telecaller", full_name: callerName, email: `ccrm002-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `NT-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E NT Counselor ${stamp}`;
  const counselor = await post({ role: "counselor", division: "it", full_name: counselorName, email: `ccrm002-c-${stamp}@example.local` });
  const other = await post({ role: "counselor", division: "it", full_name: `E2E NT Other ${stamp}`, email: `ccrm002-o-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [caller, counselor, other]) await activateWithToken(page.request, user.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the telecaller creates the lead, hands it over, and adds a note on the now read-only lead
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name: `NT Lead ${stamp}`, email: `ccrm002-l-${stamp}@example.local`, phone, product_id: products[0].id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  await page.goto(`/telecaller/leads/${id}`);
  await page.getByRole("button", { name: "Assign to counselor" }).click();
  await page.getByLabel("Counselor", { exact: true }).selectOption({ label: counselorName });
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByRole("note")).toContainText("You can view it but not change it.");
  const notes = page.getByRole("region", { name: "Notes" });
  await notes.getByLabel("Add a note").fill("Father prefers a Sunday call");
  await notes.getByRole("button", { name: "Add note" }).click();
  await expect(notes.getByRole("status")).toHaveText("Note added.");
  await expect(page.getByRole("list", { name: "Lead notes" })).toContainText("Father prefers a Sunday call");

  // the counselor adds a note and sees both, newest first, and in the activity with the author
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/leads/${id}`);
  const counselorNotes = page.getByRole("region", { name: "Notes" });
  await expect(counselorNotes.getByRole("list", { name: "Lead notes" })).toContainText("Father prefers a Sunday call");
  await counselorNotes.getByLabel("Add a note").fill("Counselling done; wants the January intake");
  await counselorNotes.getByRole("button", { name: "Add note" }).click();
  const items = counselorNotes.getByRole("list", { name: "Lead notes" }).getByRole("listitem");
  await expect(items.first()).toContainText("Counselling done; wants the January intake");
  await expect(items.first()).toContainText(counselorName);
  await expect(items.nth(1)).toContainText(callerName);
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity.getByRole("listitem").filter({ hasText: "Counselling done; wants the January intake" })).toContainText("Note added");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // another counselor: 404 for read and write
  await signIn(page, "it", other.email, E2E_PASSWORD, "/it/counselor/dashboard");
  expect((await page.request.get(`/api/v1/counselor/leads/${id}/notes`)).status()).toBe(404);
  expect((await page.request.post(`/api/v1/counselor/leads/${id}/notes`, { data: { body: "x" } })).status()).toBe(404);

  expect(consoleErrors).toEqual([]);
});
