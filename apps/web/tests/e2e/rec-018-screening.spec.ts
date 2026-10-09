import { expect, test, type Page } from "@playwright/test";

// rec-018 (AC1, AC2; SC2, SC3, SC5, SC8): the seeded recruiter screens a candidate on a requirement. Rejected without remarks is stopped;
// Hold keeps the status and flags the board; re-screening after Hold with Shortlisted moves the status and writes history; the seeded
// placement manager reads the screening without any write control.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("screening: Rejected needs remarks, Hold flags, Shortlisted moves the status; the manager reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const name = `E2E Screen ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/recruiter/") && response.status() >= 400 && failedCalls.push(`${response.status()} ${response.url()}`));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Screen Co ${stamp}` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `Java ${stamp}`, location: "Pune" } });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;

  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(`8${String(stamp).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateId = page.url().split("/").pop() as string;
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId } });
  expect(added.status()).toBe(201);

  await page.goto(`/recruiter/requirements/${requirementId}`);
  const section = page.getByRole("region", { name: /^Candidates/ });
  const toggle = section.getByRole("button", { name: `Screening of ${name}` });
  await toggle.click();
  let form = section.getByRole("form", { name: `Screening of ${name}` });

  // AC2: Rejected without remarks is stopped before any request.
  await form.getByLabel("Result").selectOption({ label: "Rejected" });
  await form.getByRole("button", { name: "Save screening" }).click();
  await expect(form.getByRole("alert")).toHaveText("Remarks are required when the result is Rejected.");

  // SC2: Hold keeps Sourced and flags the board.
  await form.getByLabel("Result").selectOption({ label: "Hold" });
  await form.getByLabel("Notice period (days)").fill("60");
  await form.getByLabel(/Recruiter remarks/).fill("Waiting for the relieving letter");
  await form.getByRole("button", { name: "Save screening" }).click();
  await expect(section.getByText(`Screening saved — ${name} is now Sourced.`)).toBeVisible();
  await expect(section.getByText("Screening: Hold")).toBeVisible();

  // AC1 + re-screening after Hold: the form is prefilled; Shortlisted moves the status and writes history.
  await toggle.click();
  form = section.getByRole("form", { name: `Screening of ${name}` });
  await expect(form.getByLabel("Notice period (days)")).toHaveValue("60");
  await form.getByLabel("Qualification verified").check();
  await form.getByLabel("Communication skills").selectOption({ label: "4 / 5" });
  await form.getByLabel("Expected salary (per year)").fill("650000");
  await form.getByLabel("Result").selectOption({ label: "Shortlisted" });
  await form.getByRole("button", { name: "Save screening" }).click();
  await expect(section.getByText(`Screening saved — ${name} is now Shortlisted.`)).toBeVisible();
  await expect(section.getByText("Screening: Shortlisted")).toBeVisible();
  await expect(section.getByText("Shortlisted", { exact: true })).toBeVisible();
  await section.getByRole("button", { name: `History of ${name}` }).click();
  await expect(section.getByText(/Sourced → Shortlisted — Screening: Shortlisted/)).toBeVisible();

  // SC8: the manager reads the summary; no Save.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const managerView = page.getByRole("region", { name: /^Candidates/ });
  await managerView.getByRole("button", { name: `Screening of ${name}` }).click();
  const summary = managerView.getByRole("list", { name: `Screening of ${name}` });
  await expect(summary).toContainText("Result: Shortlisted");
  await expect(summary).toContainText("6,50,000");
  await expect(managerView.getByRole("button", { name: "Save screening" })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
