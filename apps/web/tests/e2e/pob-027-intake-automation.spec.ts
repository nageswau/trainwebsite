import { expect, test, type Page } from "@playwright/test";

// pob-027 (DEC-SCOPE-434): the Team Lead's intake automation page (task template, escalation rules), a recruiter's new requirement with
// the template's tasks and "Mark done", and a manager's requirement for a company with no recruiter (the Team Lead queue). The escalation
// sweep runs in the worker and is asserted in test_pob_027_intake_automation.py.

async function signIn(page: Page, email: string, login = "/it/login") {
  await page.context().clearCookies();
  await page.goto(login);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";

test("intake automation: template and rules, a new requirement's tasks, and the Team Lead queue", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const failedCalls: string[] = [];
  page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && failedCalls.push(r.url()));

  // The Team Lead: the template is shown and validated, and a rule is added and switched off.
  await signIn(page, MANAGER, "/admin/login");
  await page.goto("/recruiter/manager/automation");
  await expect(page.getByRole("heading", { name: "Intake automation" })).toBeVisible();
  await expect(page.getByLabel("Task 1 title")).toHaveValue("Prepare the sourcing plan");
  await page.getByLabel("Task 2 due after (hours)").fill("0");
  await page.getByRole("button", { name: "Save tasks" }).click();
  await expect(page.getByText("Enter whole hours from 1 to 720")).toBeVisible();
  await page.getByLabel("Task 2 due after (hours)").fill("72");
  await page.getByRole("button", { name: "Save tasks" }).click();
  await expect(page.getByText("Task template saved.")).toBeVisible();
  await page.getByLabel("When", { exact: true }).selectOption("requirement_task_overdue");
  await page.getByLabel("After (hours)", { exact: true }).fill("48");
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByText("Escalation rule added.")).toBeVisible();
  const row = page.getByRole("row", { name: /Requirement task overdue.*48 h/ }).last();
  await row.getByRole("button", { name: "Switch off" }).click();
  await expect(row.getByRole("button", { name: "Switch on" })).toBeVisible();

  // A company with no recruiter: the manager's requirement waits in the Unassigned queue with no tasks.
  const orphan = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Pob027 Unowned ${stamp} Ltd` } });
  expect(orphan.status(), await orphan.text()).toBe(201);
  const orphanId = (await orphan.json()).company.id as string;
  const queued = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: orphanId, title: `Unowned ${stamp}`, location: "Pune" } });
  expect(queued.status(), await queued.text()).toBe(201);
  const queuedReq = (await queued.json()).requirement;
  expect(queuedReq.assigned_recruiter).toBeNull();
  await page.goto(`/recruiter/requirements/${queuedReq.id}`);
  await expect(page.getByText("No tasks on this requirement.")).toBeVisible();

  // The recruiter: their new requirement starts with the template's tasks; one is marked done.
  await signIn(page, RECRUITER);
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Pob027 ${stamp} Ltd` } });
  expect(company.status(), await company.text()).toBe(201);
  const companyId = (await company.json()).company.id as string;
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: companyId, title: `Intake ${stamp}`, location: "Pune" } });
  expect(created.status(), await created.text()).toBe(201);
  const requirementId = (await created.json()).requirement.id as string;
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const tasks = page.getByRole("region", { name: "Tasks" });
  await expect(tasks.getByText("Prepare the sourcing plan")).toBeVisible();
  await expect(tasks.getByText("Screen the first shortlisted profiles")).toBeVisible();
  await tasks.getByRole("button", { name: "Mark done: Prepare the sourcing plan" }).click();
  await expect(tasks.getByText("Done", { exact: true })).toBeVisible();
  await expect(tasks.getByRole("button", { name: "Mark done: Prepare the sourcing plan" })).toHaveCount(0);

  // The recruiter cannot open the Team Lead's page.
  await page.goto("/recruiter/manager/automation");
  await expect(page.getByText("Placement manager role required")).toBeVisible();

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("403"))).toEqual([]);
});
