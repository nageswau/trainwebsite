import { expect, test, type Page } from "@playwright/test";

// hrc-026 (DEC-SCOPE-394): the seeded student applies from the portal and gets a receipt with the Application ID; their Job Applications
// list shows the ID in the candidate's wording ("Received"). The seeded recruiter sees the same ID with source and owner on the board,
// moves the student's application to Profile Shared (no new candidate notice, the portal still says Received) and rejects it with a
// required reason, which shows on the row and in History but never in the portal.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const STUDENT = "student.it@edusphere.local";

test("application record: code, receipt, internal stage hidden, rejection reason", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const title = `E2E Record Analyst ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  // The recruiter opens a requirement the student can see.
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Record ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title, location: "Pune" } });
  expect(created.ok()).toBeTruthy();
  const requirement = (await created.json()).requirement;
  if (requirement.status === "new") { // hrc-007: a recruiter's requirement starts as New; open it (the hrc-008 spec's idiom)
    const opened = await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } });
    expect(opened.ok()).toBeTruthy();
  }

  // The student applies (AC4: a receipt with the Application ID).
  await page.context().clearCookies();
  await signIn(page, "it", STUDENT, "/it/student/dashboard");
  const applied = await page.request.post(`/api/v1/workflows/it/jobs/${requirement.id}/apply`, { data: {} });
  expect(applied.status()).toBe(201);
  const code = (await applied.json()).code as string;
  expect(code).toMatch(/^JA-\d{6,}$/);
  await page.goto("/it/student/notifications");
  await expect(page.getByText(`We received your application ${code} for ${title}`).first()).toBeVisible();
  await page.goto("/it/student/job-applications");
  const row = page.getByRole("row").filter({ hasText: code });
  await expect(page.getByRole("columnheader", { name: "Application ID" })).toBeVisible();
  await expect(row).toContainText("Received");

  // The recruiter sees the ID, source and owner, and moves it to the internal Profile Shared stage.
  await page.context().clearCookies();
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const section = page.getByRole("region", { name: /^Candidates/ });
  const item = section.getByRole("listitem").filter({ hasText: code });
  await expect(item).toContainText("Source: Candidate portal");
  const name = (await item.getByRole("link").first().textContent())!.trim();
  await item.getByRole("button", { name: `Change status of ${name}` }).click();
  let form = section.getByRole("form", { name: `Change status of ${name}` });
  await form.getByLabel("New status").selectOption({ label: "Profile Shared" });
  await expect(form.getByLabel("Rejection reason")).toHaveCount(0);
  await form.getByRole("button", { name: "Save status" }).click();
  await expect(section.getByText(`${name} is now Profile Shared.`)).toBeVisible();

  // AC3: Rejected needs a reason; Save stays disabled until one is chosen.
  await item.getByRole("button", { name: `Change status of ${name}` }).click();
  form = section.getByRole("form", { name: `Change status of ${name}` });
  await form.getByLabel("New status").selectOption({ label: "Rejected" });
  await expect(form.getByRole("button", { name: "Save status" })).toBeDisabled();
  await form.getByLabel("Rejection reason").selectOption({ label: "Skills do not match" });
  await form.getByRole("button", { name: "Save status" }).click();
  await expect(section.getByText(`${name} is now Rejected.`)).toBeVisible();
  await expect(item).toContainText("Reason: Skills do not match");
  await item.getByRole("button", { name: `History of ${name}` }).click();
  await expect(item.getByText(/Profile Shared → Rejected \(Skills do not match\)/)).toBeVisible();

  // AC2: the student got no notice for Profile Shared -- only the receipt and the rejection; the reason never reaches them.
  await page.context().clearCookies();
  await signIn(page, "it", STUDENT, "/it/student/dashboard");
  const notices = await page.request.get("/api/v1/workflows/notifications");
  expect(notices.ok()).toBeTruthy();
  const text = JSON.stringify(await notices.json());
  expect(text).toContain(`We received your application ${code}`);
  expect(text).not.toContain("Profile Shared");
  expect(text).not.toContain("Skills do not match");
  await page.goto("/it/student/job-applications");
  await expect(page.getByRole("row").filter({ hasText: code })).toContainText("Rejected");
  await expect(page.getByText("Skills do not match")).toHaveCount(0);

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
