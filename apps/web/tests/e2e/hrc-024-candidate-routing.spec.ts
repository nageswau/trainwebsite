import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// hrc-024 (DEC-SCOPE-393): a placement manager adds a Website source rule on Candidate Routing; the next website applicant is routed to
// that recruiter (AC1, history "Automatic routing"). With the rule deleted, the next applicant waits in the unassigned queue and the
// manager is alerted (AC3). A recruiter cannot open the page (R11). Routing is global: the spec clears it first and leaves it clear.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function created(page: Page, data: Record<string, unknown>) {
  const response = await page.request.post("/api/v1/admin/users", { data });
  expect(response.ok(), await response.text()).toBe(true);
  return { ...(await response.json()), full_name: data.full_name as string, email: data.email as string };
}

async function clearRouting(page: Page) {
  const routing = await (await page.request.get("/api/v1/recruiter/candidate-routing")).json();
  for (const rule of routing.rules) await page.request.delete(`/api/v1/recruiter/candidate-routing/rules/${rule.id}`);
  await page.request.put("/api/v1/recruiter/candidate-routing", { data: { default_recruiter_user_id: null, strategy: "round_robin" } });
}

async function apply(page: Page, jobId: string, email: string) {
  const response = await page.request.post(`/api/v1/public/jobs/${jobId}/apply`, {
    data: { full_name: `E2E H24 ${email.slice(0, 14)}`, email, phone: null, resume_url: "/local-files/career-resumes/x.pdf", cover_note: "Hi" },
    headers: { "X-Forwarded-For": `10.24.${Date.now() % 250}.${Math.floor(Math.random() * 250)}` },
  });
  expect(response.status(), await response.text()).toBe(201);
  const found = await (await page.request.get(`/api/v1/recruiter/candidates?q=${encodeURIComponent(email)}`)).json();
  return found.items[0];
}

test("a manager's Website rule routes applicants; without a rule they wait in the queue and the manager is alerted", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const manager = await created(page, { role: "placement_manager", division: "global", full_name: `E2E H24 Manager ${stamp}`, email: `hrc024-m-${stamp}@example.local` });
  const recruiter = await created(page, { role: "placement_team", full_name: `E2E H24 Ravi ${stamp}`, email: `hrc024-r-${stamp}@example.local`,
    recruiter_profile: { employee_id: `H24-${stamp}`, reporting_manager_user_id: manager.id } });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, recruiter]) await activateWithToken(page.request, user.development_welcome_token);

  await signIn(page, "/admin/login", manager.email);
  await clearRouting(page);
  await page.goto("/recruiter/manager/routing");
  await expect(page.getByRole("heading", { name: "Candidate routing" })).toBeVisible();
  await expect(page.getByText("No rules yet")).toBeVisible();

  await page.getByLabel("Rule type").selectOption("source");
  await page.locator("#routing-value").selectOption({ label: "Website" });
  await page.locator("#routing-recruiter").fill(`Ravi ${stamp}`);
  await page.getByRole("option", { name: new RegExp(recruiter.full_name) }).click();
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByText("Rule added.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Routing rules" })).toContainText(recruiter.full_name);

  const jobs = await (await page.request.get("/api/v1/public/jobs")).json();
  expect(jobs.length, "a public job must be open").toBeGreaterThan(0);
  const routed = await apply(page, jobs[0].id, `hrc024-a-${stamp}@example.com`);
  expect(routed.owner?.id).toBe(recruiter.id);
  await page.goto(`/recruiter/candidates/${routed.id}`);
  await expect(page.getByText("Automatic routing").first()).toBeVisible({ timeout: 20_000 });

  page.once("dialog", (dialog) => dialog.accept());
  await page.goto("/recruiter/manager/routing");
  await page.getByRole("button", { name: /Delete rule Candidate source Website/ }).click();
  await expect(page.getByText("No rules yet")).toBeVisible();
  const waiting = await apply(page, jobs[0].id, `hrc024-b-${stamp}@example.com`);
  expect(waiting.owner).toBeNull();
  const inbox = await (await page.request.get("/api/v1/workflows/notifications")).json();
  const items = Array.isArray(inbox) ? inbox : inbox.items;
  expect(items.some((n: { title: string; action_url: string }) => n.title === "Candidate needs a recruiter" && n.action_url === "/recruiter/candidates?owner=unassigned")).toBe(true);
  await page.goto("/recruiter/candidates?owner=unassigned");
  await expect(page.getByText(waiting.name).first()).toBeVisible({ timeout: 20_000 });

  await signIn(page, "/it/login", recruiter.email);
  await page.goto("/recruiter/manager/routing");
  await expect(page.getByText("Placement manager role required")).toBeVisible();
  expect((await page.request.get("/api/v1/recruiter/candidate-routing")).status()).toBe(403);
});
