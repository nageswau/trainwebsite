import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// hrc-016 (DEC-SCOPE-385): a recruiter writes a private note and hands a teammate a resume-screening task from the candidate page; both
// show on the timeline (AC3). The teammate finds the task under My tasks (AC2) and marks it done, which the candidate's timeline then shows.
// The cards fit a phone.

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
  const manager = await post(page, "/api/v1/admin/users", { role: "placement_manager", division: "global", full_name: `E2E H16 Manager ${stamp}`, email: `hrc016-m-${stamp}@example.local` });
  const recruiter = (suffix: string, name: string) => post(page, "/api/v1/admin/users", {
    role: "placement_team", full_name: `${name} ${stamp}`, email: `hrc016-${suffix}-${stamp}@example.local`,
    recruiter_profile: { employee_id: `H16-${stamp}-${suffix}`, reporting_manager_user_id: manager.id },
  });
  const writer = await recruiter("a", "E2E Writer");
  const doer = await recruiter("b", "E2E Doer");
  await page.request.post("/api/v1/auth/logout");
  for (const user of [writer, doer]) await activateWithToken(page.request, user.development_welcome_token);
  return { writer, doer };
}

test("a private note and a task reach the timeline, the assignee's My tasks, and Done", async ({ page }) => {
  const stamp = Date.now();
  const { writer, doer } = await setUp(page, stamp);
  const name = `E2E Noted ${stamp}`;
  const doerName = `E2E Doer ${stamp}`;

  await signIn(page, "/it/login", writer.email);
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const candidate = await post(page, "/api/v1/recruiter/candidates", { name, email: `hrc016-c-${stamp}@example.com`, source_id: sources.items[0].id });
  await page.goto(`/recruiter/candidates/${candidate.id}`);

  const notes = page.getByRole("region", { name: "Notes" });
  await expect(notes).toContainText("No notes yet.");
  await expect(notes).toContainText("never shown to candidates or employers");
  await notes.getByLabel("New note").fill("Prefers Pune; call after 6 pm");
  await notes.getByRole("button", { name: "Add note" }).click();
  await expect(notes.getByRole("list", { name: "Candidate notes" })).toContainText("Prefers Pune; call after 6 pm");

  const tasks = page.getByRole("region", { name: "Tasks" });
  await tasks.getByRole("button", { name: "Add task" }).click();
  const form = tasks.getByRole("form", { name: "Add task" });
  await form.getByLabel("Type (required)").selectOption("resume_screening");
  await form.getByLabel("Title (required)").fill("Screen the resume");
  const due = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
  await form.getByLabel("Due date and time (IST, required)").fill(`${due}T10:30`);
  await form.getByRole("combobox", { name: "Assigned to (required)" }).fill(doerName);
  await page.getByRole("option", { name: new RegExp(doerName) }).click();
  await form.getByRole("button", { name: "Add task" }).click();
  await expect(tasks).toContainText("Task added.");
  const list = tasks.getByRole("list", { name: "Candidate tasks" });
  await expect(list).toContainText("Screen the resume");
  await expect(list).toContainText(doerName);

  const timeline = page.getByRole("region", { name: "Timeline" });
  await expect(timeline).toContainText("Note added");
  await expect(timeline).toContainText("Task assigned: Resume screening");
  await expect(timeline).toContainText("Candidate added");
  await expect(timeline).toContainText(/Primary recruiter: None → E2E Writer/);

  await signIn(page, "/it/login", doer.email);
  await page.goto("/recruiter/tasks?due=upcoming");
  const mine = page.getByRole("list", { name: "My tasks" });
  const item = mine.getByRole("listitem").filter({ hasText: name });
  await expect(item).toContainText("Screen the resume");
  await item.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Task marked done.")).toBeVisible();
  await expect(mine.getByRole("listitem").filter({ hasText: name })).toHaveCount(0);

  await page.goto(`/recruiter/candidates/${candidate.id}`);
  await expect(page.getByRole("region", { name: "Timeline" })).toContainText("Task done: Resume screening");

  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  for (const card of ["Notes", "Tasks"]) {
    const box = await page.getByRole("region", { name: card }).boundingBox();
    expect(box && box.x >= 0 && box.x + box.width <= 375).toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
