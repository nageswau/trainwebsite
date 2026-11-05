import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// hrc-025 (DEC-SCOPE-402): a website applicant appears in New Website Registrations on the next load (AC1), in the Unassigned view
// (AC2, kept in the URL across a refresh), "Not contacted"; a logged call sets the first contact (AC3). The HR Manager reads the list
// without a link to the candidate (N2); a phone shows the table inside its own scroll area. Routing is global: the spec clears it first.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function clearRouting(page: Page) {
  const routing = await (await page.request.get("/api/v1/recruiter/candidate-routing")).json();
  for (const rule of routing.rules) await page.request.delete(`/api/v1/recruiter/candidate-routing/rules/${rule.id}`);
  await page.request.put("/api/v1/recruiter/candidate-routing", { data: { default_recruiter_user_id: null, strategy: "round_robin" } });
}

test("a website applicant is listed, filtered as unassigned, and a logged call sets the first contact; the HR Manager reads the list", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const response = await page.request.post("/api/v1/admin/users", { data: { role: "placement_manager", division: "global", full_name: `E2E H25 Manager ${stamp}`, email: `hrc025-m-${stamp}@example.local` } });
  expect(response.ok(), await response.text()).toBe(true);
  const manager = { ...(await response.json()), email: `hrc025-m-${stamp}@example.local` };
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);

  await signIn(page, "/admin/login", manager.email);
  await clearRouting(page);
  const jobs = await (await page.request.get("/api/v1/public/jobs")).json();
  expect(jobs.length, "a public job must be open").toBeGreaterThan(0);
  const name = `E2E H25 Web ${stamp}`;
  const applied = await page.request.post(`/api/v1/public/jobs/${jobs[0].id}/apply`, {
    data: { full_name: name, email: `hrc025-a-${stamp}@example.com`, phone: null, resume_url: "/local-files/career-resumes/x.pdf", cover_note: "Hi" },
    headers: { "X-Forwarded-For": `10.25.${stamp % 250}.${Math.floor(Math.random() * 250)}` },
  });
  expect(applied.status(), await applied.text()).toBe(201);

  // AC1 + AC2: listed on the next load, in the Unassigned view; the view survives a refresh.
  await page.goto("/recruiter/website-registrations");
  await expect(page.getByRole("heading", { name: "New website registrations" })).toBeVisible();
  await page.getByLabel("Show").selectOption("unassigned");
  await expect(page).toHaveURL(/view=unassigned/);
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row).toContainText("Not contacted");
  await expect(row).toContainText("Unassigned");
  await expect(row).toContainText("Applied");
  await page.reload();
  await expect(page.getByLabel("Show")).toHaveValue("unassigned");
  await page.getByLabel("Show").selectOption("active"); // hrc-021: a website application in the last 30 days is Active
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText("Active");
  await page.getByLabel("Show").selectOption("new");
  await expect(page.getByRole("row", { name: new RegExp(name) })).toHaveCount(0);

  // AC3: a call logged on the candidate is the first contact.
  await page.goto("/recruiter/website-registrations");
  await page.getByRole("link", { name }).click();
  await expect(page).toHaveURL(/\/recruiter\/candidates\/[0-9a-f-]+$/);
  const calls = page.getByRole("region", { name: "Calls" });
  await calls.getByRole("button", { name: "Log call" }).click();
  const form = calls.getByRole("form", { name: "Log call" });
  await form.getByLabel("Outcome (required)").selectOption("no_answer");
  await form.getByRole("button", { name: "Save call" }).click();
  await expect(calls.getByText("Call logged.")).toBeVisible();
  await page.goto("/recruiter/website-registrations?view=unassigned");
  const contacted = page.getByRole("row", { name: new RegExp(name) });
  await expect(contacted).toBeVisible();
  await expect(contacted).not.toContainText("Not contacted");
  await expect(contacted).not.toContainText("SLA breached");

  // N2: the HR Manager reads all, with no link to the candidate; a phone scrolls the table, not the page.
  await signIn(page, "/it/login", "hr.manager@edusphere.local", "Demo@123");
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/recruiter/website-registrations");
  const hrRow = page.getByRole("row", { name: new RegExp(name) });
  await expect(hrRow).toBeVisible();
  await expect(hrRow.getByRole("link")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
