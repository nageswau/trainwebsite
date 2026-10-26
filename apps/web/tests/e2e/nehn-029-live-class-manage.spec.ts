import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// nehn-029 -- live class reschedule and cancel. Each test creates its own throwaway upcoming session through the real API (RAID I-10),
// then drives the trainer's "Live sessions" page; the student sees the cancellation with its reason and no join button.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
  const access = (await page.context().cookies()).find((c) => c.name === "edusphere_access")?.value;
  return { cookie: `edusphere_access=${access}` };
}

async function createSession(request: APIRequestContext, headers: { cookie: string }, title: string) {
  const context = await request.get("/api/v1/workflows/it/trainer/context", { headers });
  const batchId = (await context.json()).batches[0]?.id;
  const starts = new Date(Date.now() + 2 * 86400000);
  starts.setUTCSeconds(0, 0);
  const created = await request.post("/api/v1/communications/it/live-sessions", {
    headers,
    data: { batch_id: batchId, title, starts_at: starts.toISOString(), ends_at: new Date(starts.getTime() + 3600000).toISOString(), provider: "manual", meeting_url: "https://meet.example.com/nehn-029" },
  });
  expect(created.ok()).toBeTruthy();
}

function manageCard(page: Page, title: string) {
  return page.locator("section.card", { has: page.getByRole("heading", { name: title, exact: true }) });
}

test("trainer moves a class by one hour and the new time is shown", async ({ page, request }) => {
  const headers = await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  const title = `N029 move ${Date.now()}`;
  await createSession(request, headers, title);

  await page.goto("/it/trainer/live-sessions");
  const card = manageCard(page, title);
  await card.getByRole("button", { name: "Reschedule" }).click();
  const start = card.getByLabel(/^Starts/);
  const end = card.getByLabel(/^Ends/);
  const bump = (value: string) => value.replace(/T(\d\d)/, (_, h) => `T${String((Number(h) + 1) % 24).padStart(2, "0")}`);
  const newStart = bump(await start.inputValue());
  await start.fill(newStart);
  await end.fill(bump(await end.inputValue()));
  await card.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Live class updated" })).toBeVisible();

  await manageCard(page, title).getByRole("button", { name: "Reschedule" }).click();
  await expect(manageCard(page, title).getByLabel(/^Starts/)).toHaveValue(newStart);
});

test("trainer cancels with a reason; the student sees Cancelled with the reason and cannot join", async ({ page, request, browser }) => {
  const headers = await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  const title = `N029 cancel ${Date.now()}`;
  await createSession(request, headers, title);

  await page.goto("/it/trainer/live-sessions");
  const card = manageCard(page, title);
  await card.getByRole("button", { name: "Cancel class" }).click();
  await card.getByLabel("Reason learners will see").fill("Public holiday");
  await card.getByRole("button", { name: "Confirm cancellation" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Live class cancelled" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: title })).toContainText("Public holiday");

  const student = await browser.newPage();
  await signIn(student, "student.it@edusphere.local", "/it/student/dashboard");
  await student.goto("/it/student/course");
  const studentCard = student.locator(".card", { has: student.getByRole("heading", { name: title, exact: true }) });
  await expect(studentCard.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(studentCard).toContainText("Public holiday");
  await expect(studentCard.getByRole("button", { name: "Join class" })).toHaveCount(0);
});

test("the cancel API refuses a student with 403", async ({ page, request }) => {
  const trainer = await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  const title = `N029 forbidden ${Date.now()}`;
  await createSession(request, trainer, title);
  const id = (await (await request.get("/api/v1/communications/it/live-sessions", { headers: trainer })).json()).find((s: { title: string }) => s.title === title).id;
  await page.context().clearCookies();
  const student = await signIn(page, "student.it@edusphere.local", "/it/student/dashboard");
  const refused = await request.post(`/api/v1/communications/it/live-sessions/${id}/cancel`, { headers: student, data: { reason: "Not mine" } });
  expect(refused.status()).toBe(403);
});
