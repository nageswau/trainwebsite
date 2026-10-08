import { expect, test, type Page } from "@playwright/test";

// rec-017 (AC1, AC2; A2): the seeded recruiter adds one candidate to two requirements (ABC and XYZ), moves ABC to Interview and rejects
// XYZ; adding them to ABC again is refused; Joined is refused until Selected; the candidate's Applications section shows a different status
// per company; the seeded placement manager reads the candidates without any write control.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

async function requirement(page: Page, company: string, title: string): Promise<string> {
  const created = await page.request.post("/api/v1/recruiter/companies", { data: { name: company } });
  expect(created.ok()).toBeTruthy();
  const response = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await created.json()).company.id, title, location: "Pune" } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).requirement.id as string;
}

async function changeStatus(page: Page, name: string, status: string) {
  const section = page.getByRole("region", { name: /^Candidates/ });
  await section.getByRole("button", { name: `Change status of ${name}` }).click();
  const form = section.getByRole("form", { name: `Change status of ${name}` });
  await form.getByLabel("New status").selectOption({ label: status });
  await form.getByRole("button", { name: "Save status" }).click();
  return form;
}

test("tracking: one candidate, two requirements, different statuses; duplicate refused; Joined gated; the manager reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const name = `E2E Rahul ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/recruiter/") && response.status() >= 500 && failedCalls.push(response.url()));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const abc = await requirement(page, `E2E ABC ${stamp} Ltd`, `Java Developer ${stamp}`);
  const xyz = await requirement(page, `E2E XYZ ${stamp} Corp`, `QA Engineer ${stamp}`);

  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(`9${String(stamp).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateUrl = page.url();
  await expect(page.getByRole("region", { name: "Applications" }).getByText("Not on any job requirement yet.")).toBeVisible();

  for (const [id, start] of [[abc, "Sourced"], [xyz, "Shortlisted"]] as const) {
    await page.goto(`/recruiter/requirements/${id}`);
    const section = page.getByRole("region", { name: /^Candidates/ });
    await expect(section.getByText("No candidates on this requirement yet.")).toBeVisible();
    await section.getByRole("button", { name: "Add candidate" }).click();
    const form = section.getByRole("form", { name: "Add candidate" });
    await form.getByRole("combobox", { name: "Candidate" }).fill(name);
    await page.getByRole("option", { name: new RegExp(name) }).click();
    await form.getByLabel("Starting status").selectOption({ label: start });
    await form.getByRole("button", { name: "Add candidate" }).click();
    await expect(section.getByText(`${name} added as ${start}.`)).toBeVisible();
    await expect(section.getByRole("heading", { name: "Candidates (1)" })).toBeVisible();
  }

  // XYZ: Rejected.
  await changeStatus(page, name, "Rejected");
  await expect(page.getByText(`${name} is now Rejected.`)).toBeVisible();

  // ABC: Sourced -> Interview; Joined is not offered before Selected; history lists every change.
  await page.goto(`/recruiter/requirements/${abc}`);
  await changeStatus(page, name, "Interview");
  const section = page.getByRole("region", { name: /^Candidates/ });
  await expect(section.getByText(`${name} is now Interview.`)).toBeVisible();
  await section.getByRole("button", { name: `Change status of ${name}` }).click();
  const options = await section.getByRole("form", { name: `Change status of ${name}` }).getByLabel("New status").locator("option").allTextContents();
  expect(options).not.toContain("Joined");
  await section.getByRole("button", { name: "Cancel" }).click();
  await section.getByRole("button", { name: `History of ${name}` }).click();
  await expect(section.getByText(/Sourced → Interview/)).toBeVisible();
  await expect(section.getByText(/Added as Sourced/)).toBeVisible();

  // AC2: adding them again is refused by the API with its message.
  await section.getByRole("button", { name: "Add candidate" }).click();
  const again = section.getByRole("form", { name: "Add candidate" });
  const box = again.getByRole("combobox", { name: "Candidate" });
  await box.fill(name); // keyboard only: pick with ArrowDown + Enter, submit with Enter on the button
  await expect(page.getByRole("option", { name: new RegExp(name) })).toBeVisible();
  await box.press("ArrowDown");
  await box.press("Enter");
  await expect(box).toHaveValue(new RegExp(name));
  await again.getByRole("button", { name: "Add candidate" }).press("Enter");
  await expect(again.getByRole("alert")).toHaveText("This candidate is already on this requirement");

  // AC1: the candidate's Applications show a different status per company.
  await page.goto(candidateUrl);
  const applications = page.getByRole("region", { name: "Applications" });
  await expect(applications.getByRole("listitem").filter({ hasText: `E2E ABC ${stamp}` })).toContainText("Interview");
  await expect(applications.getByRole("listitem").filter({ hasText: `E2E XYZ ${stamp}` })).toContainText("Rejected");

  // The manager reads; no Add candidate, no Change status.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(`/recruiter/requirements/${abc}`);
  const managerView = page.getByRole("region", { name: /^Candidates/ });
  await expect(managerView.getByText("Interview", { exact: true })).toBeVisible();
  await expect(managerView.getByRole("button", { name: "Add candidate" })).toHaveCount(0);
  await expect(managerView.getByRole("button", { name: /Change status/ })).toHaveCount(0);
  // The 409 for the duplicate is an expected API refusal (logged by the browser as a failed resource), not a page error.
  expect(consoleErrors.filter((text) => !text.includes("409"))).toEqual([]);
  expect(failedCalls).toEqual([]);
});
