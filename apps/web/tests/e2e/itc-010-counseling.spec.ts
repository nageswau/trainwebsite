import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-010 (DEC-SCOPE-343): the IT counselor a lead is handed to records a counseling session (course, objection, fee, joining date,
// decision-maker, outcome), edits it, and sees it in the timeline; the telecaller reads it with no controls; another counselor is 404;
// the manager manages the objections list. Throwaway accounts; phone width has no sideways scroll; no console errors.
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
const istDay = (offset: number) => new Date(Date.now() + 5.5 * 3600_000 + offset * 86_400_000).toISOString().slice(0, 10);

test("the IT counselor records and edits a counseling session; the telecaller reads it", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post("/api/v1/admin/users", { role: "telecaller_manager", division: "global", full_name: `E2E CS Manager ${stamp}`, email: `itc010-m-${stamp}@example.local` });
  const caller = await post("/api/v1/admin/users", {
    role: "telecaller", full_name: `E2E CS Telecaller ${stamp}`, email: `itc010-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `CS-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E CS Counselor ${stamp}`;
  const counselor = await post("/api/v1/admin/users", { role: "counselor", division: "it", full_name: counselorName, email: `itc010-c-${stamp}@example.local` });
  const other = await post("/api/v1/admin/users", { role: "counselor", division: "it", full_name: `E2E CS Other ${stamp}`, email: `itc010-o-${stamp}@example.local` });
  const course = await post("/api/v1/telecaller/products", { group: "it", name: `Python Full Stack ${stamp}` });
  const overseas = await post("/api/v1/telecaller/products", { group: "overseas", name: `UK Masters ${stamp}` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, caller, counselor, other]) await activateWithToken(page.request, user.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the manager adds an objection to the managed list
  const objection = `Prefers weekends ${stamp}`;
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/telecaller/manager/team");
  await page.goto("/telecaller/manager/counseling-objections");
  await expect(page.getByRole("heading", { name: "Counseling objections" })).toBeVisible();
  await page.getByLabel("Name (required)").fill(objection);
  await page.getByRole("button", { name: "Create objection" }).click();
  await expect(page.getByText(`Created ${objection}.`)).toBeVisible();

  // the telecaller creates the lead and hands it over
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name: `CS Lead ${stamp}`, email: `itc010-l-${stamp}@example.local`, phone, product_id: course.id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;
  await page.goto(`/telecaller/leads/${id}`);
  await page.getByRole("button", { name: "Assign to counselor" }).click();
  await page.getByLabel("Counselor", { exact: true }).selectOption({ label: counselorName });
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByRole("note")).toContainText("You can view it but not change it.");

  // the counselor records a session
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  await page.goto(`/it/counselor/leads/${id}`);
  const section = page.getByRole("region", { name: "Counseling" });
  await expect(section.getByText("No counseling recorded yet.")).toBeVisible();
  await section.getByRole("button", { name: "Record counseling" }).click();
  const form = section.getByRole("form", { name: "Record counseling" });
  await expect(form.getByRole("option", { name: course.name })).toHaveCount(1);
  await expect(form.getByRole("option", { name: overseas.name })).toHaveCount(0); // IT courses only
  await form.getByRole("button", { name: "Save counseling" }).click();
  await expect(form.getByText("Choose the counseling outcome")).toBeVisible();
  await form.getByLabel("Outcome (required)").selectOption("interested");
  await form.getByLabel("Recommended course").selectOption({ label: course.name });
  await form.getByLabel(objection).check();
  await form.getByLabel("Course fee quoted (₹)").fill("45000");
  await form.getByLabel("Expected joining date").fill(istDay(10));
  await form.getByLabel("Decision-maker").selectOption("parent");
  await form.getByLabel("Counselor notes").fill("Parent will pay in two parts");
  await form.getByRole("button", { name: "Save counseling" }).click();
  await expect(section.getByText("Counseling recorded.")).toBeVisible();
  const card = section.getByRole("list", { name: "Counseling sessions" }).getByRole("listitem");
  await expect(card).toContainText(course.name);
  await expect(card).toContainText("₹45,000.00");
  await expect(card).toContainText("Parent");
  await expect(card).toContainText(objection);
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity).toContainText("Counseling recorded: Interested");

  // ...edits it
  await card.getByRole("button", { name: /Edit counseling/ }).click();
  const edit = section.getByRole("form", { name: "Edit counseling" });
  await edit.getByLabel("Outcome (required)").selectOption("needs_time");
  await edit.getByRole("button", { name: "Save counseling" }).click();
  await expect(section.getByText("Counseling saved.")).toBeVisible();
  await expect(card).toContainText("Needs time");
  await expect(activity).toContainText("Counseling updated: Needs time");

  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page)).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // the telecaller reads it, read only
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  await page.goto(`/telecaller/leads/${id}`);
  const readOnly = page.getByRole("region", { name: "Counseling" });
  await expect(readOnly).toContainText(course.name);
  await expect(readOnly.getByRole("button")).toHaveCount(0);

  // another counselor: 404
  await signIn(page, "it", other.email, E2E_PASSWORD, "/it/counselor/dashboard");
  expect((await page.request.get(`/api/v1/counselor/leads/${id}/counseling`)).status()).toBe(404);
  expect((await page.request.post(`/api/v1/counselor/leads/${id}/counseling`, { data: { outcome: "interested" } })).status()).toBe(404);

  expect(consoleErrors).toEqual([]);
});
