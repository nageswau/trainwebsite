import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// nehn-031 (DEC-ROLE-003, DEC-SCOPE-294): the trainer recommends a learner, the coordinator issues from the queue with an override
// reason, the student's certificate appears in the issued list; trainer and IT admin can no longer issue; the IT admin sets thresholds.
// Each run registers a fresh student and enrols them in the demo trainer's batch, so it can be repeated on one database.

const DEMO = "Demo@123";
const STUDENT_PASSWORD = "Sup3r-Secret-Pass!";

async function api(browser: Browser, email: string, password = DEMO): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password, division: "it" } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", DEMO);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function freshLearner(browser: Browser): Promise<{ name: string; enrollmentId: string }> {
  const trainer = await api(browser, "trainer@edusphere.local");
  const batchId = ((await (await trainer.get("/api/v1/workflows/it/trainer/context")).json()) as { batches: { id: string }[] }).batches[0].id;
  const stamp = Date.now();
  const name = `N031 Learner ${stamp}`;
  const email = `n031-${stamp}@example.com`;
  const context = await browser.newContext();
  const registered = await context.request.post("/api/v1/auth/register", { data: { email, password: STUDENT_PASSWORD, full_name: name, division: "it", account_type: "student" } });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  const student = await api(browser, email, STUDENT_PASSWORD);
  const enrolled = await student.post("/api/v1/workflows/it/enrollments", { data: { batch_id: batchId } });
  expect(enrolled.status(), await enrolled.text()).toBe(201);
  const agreement = await (await student.get("/api/v1/workflows/it/student/agreements/current")).json();
  expect((await student.post(`/api/v1/workflows/it/student/agreements/${agreement.id}/accept`)).ok()).toBeTruthy();
  return { name, enrollmentId: (await enrolled.json()).id };
}

test("trainer recommends, coordinator issues from the queue with an override reason", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const { name, enrollmentId } = await freshLearner(browser);

  // Trainer: recommend on the Student progress page.
  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/student-progress");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Recommend for certificate" }) });
  await expect(page.getByRole("button", { name: "Issue certificate" })).toHaveCount(0);
  await card.getByLabel("Learner").selectOption({ value: enrollmentId });
  await expect(card.getByText(/Not yet eligible: progress 0% \(needs 100%\)/)).toBeVisible();
  await card.getByLabel("Comment (optional)").fill("Finished the capstone early.");
  await card.getByRole("button", { name: "Send recommendation" }).click();
  await expect(page.getByText("Recommended to the coordinator.")).toBeVisible();

  // Trainer and IT admin are refused by the issue routes (AC1).
  const trainer = await api(browser, "trainer@edusphere.local");
  expect((await trainer.post(`/api/v1/workflows/it/certificates/${enrollmentId}/issue`, { data: {} })).status()).toBe(403);
  const admin = await api(browser, "itadmin@edusphere.local");
  expect((await admin.post("/api/v1/workflows/it/certificates/issue", { data: { enrollment_ids: [enrollmentId] } })).status()).toBe(403);

  // Coordinator: the queue shows the recommendation; issuing a learner who is not eligible asks for a reason.
  await signIn(page, "coordinator@edusphere.local", "/it/coordinator/dashboard");
  await page.goto("/it/coordinator/certificates");
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row.getByText("Not eligible")).toBeVisible();
  await expect(row.getByText("Finished the capstone early.")).toBeVisible();
  await row.getByLabel(`Select ${name}`).check();
  await page.getByLabel(/Override reason/).fill("   "); // empty is stopped by the browser (`required`); whitespace by the form
  await page.getByRole("button", { name: "Issue selected (1)" }).click();
  await expect(page.locator(".certificate-queue").getByRole("alert")).toHaveText("Enter a reason for the override.");
  await page.getByLabel(/Override reason/).fill("Trainer recommended; capstone reviewed.");
  await page.getByRole("button", { name: "Issue selected (1)" }).click();
  await expect(page.getByText("Issued 1 certificate.")).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(name) }).getByLabel(`Select ${name}`)).toHaveCount(0); // left the queue
  await page.reload();
  await page.getByLabel("Search records").fill(name); // the issued list pages 10 rows; many share today's date
  await expect(page.getByRole("cell", { name }).first()).toBeVisible(); // now in the issued list

  // A second issue is a duplicate (AC6).
  const coordinator = await api(browser, "coordinator@edusphere.local");
  expect((await coordinator.post(`/api/v1/workflows/it/certificates/${enrollmentId}/issue`, { data: {} })).status()).toBe(409);
  expect(consoleErrors).toEqual([]);
});

test("on a phone the queue stacks without sideways scrolling and the row checkbox stays reachable (QA31-06)", async ({ browser, page }) => {
  await freshLearner(browser); // the queue is never empty, whatever ran before
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "coordinator@edusphere.local", "/it/coordinator/dashboard");
  await page.goto("/it/coordinator/certificates");
  const scroll = page.locator(".certificate-queue .table-scroll");
  await expect(scroll.locator("tbody tr").first()).toBeVisible();
  expect(await scroll.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  const checkbox = scroll.locator("tbody tr").first().locator("input[type=checkbox]");
  await checkbox.scrollIntoViewIfNeeded();
  await expect(checkbox).toBeInViewport();
  await page.screenshot({ path: test.info().outputPath("queue-phone.png") });
});

test("the IT admin's Certificates page sets the thresholds instead of issuing", async ({ page }) => {
  await signIn(page, "itadmin@edusphere.local", "/it/admin/dashboard");
  await page.goto("/it/admin/certificates");
  await expect(page.getByRole("heading", { name: "Certificate rules" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Issue certificate" })).toHaveCount(0);
  const progress = page.getByLabel("Minimum progress (%)");
  await expect(progress).toHaveValue("100");
  await page.getByLabel("Minimum attendance (%)").fill("75"); // the same values: the rules row is shared by every spec
  await page.getByRole("button", { name: "Save rules" }).click();
  await expect(page.getByText("Certificate rules saved. They apply to the next eligibility check.")).toBeVisible();
});
