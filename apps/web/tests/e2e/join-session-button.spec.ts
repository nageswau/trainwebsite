import { test, expect, type Page } from "@playwright/test";

// User-requested join-experience fix (2026-09-09, `docs/decisions/PENDING_ZOHO_LIVE_CLASSES.md`
// §1b items a/b/c). Confirms the real `<button>` join experience end to end, using its
// own controlled throwaway sessions (never the shared, timing-fragile seeded one, same
// convention `trn-003-upcoming-sessions.spec.ts` now follows for the same reason):
// clicking >15 minutes before start shows a "too early" pop-up, clicking after the
// session's end time shows a "completed" pop-up, and clicking within the joinable
// window asks a joining student to confirm their own identity before the real link opens.

async function loginAndCreateSession(page: Page, request: import("@playwright/test").APIRequestContext, title: string, startsAt: Date, endsAt: Date) {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access")?.value;
  const context = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${access}` } });
  const batchId = (await context.json()).batches[0]?.id;

  // A real, same-origin, always-resolvable URL -- an external placeholder domain (e.g.
  // meet.example.com) doesn't resolve inside the test browser, so a real `window.open`
  // navigation to it fails before `popup.url()` can be read back reliably.
  const appBaseUrl = process.env.E2E_BASE_URL || "http://localhost:3000";
  const created = await request.post("/api/v1/communications/it/live-sessions", {
    headers: { cookie: `edusphere_access=${access}` },
    data: { batch_id: batchId, title, starts_at: startsAt.toISOString(), ends_at: endsAt.toISOString(), provider: "manual", meeting_url: `${appBaseUrl}/it/login?e2e=join-button-check` },
  });
  expect(created.ok()).toBeTruthy();
}

async function loginAsStudent(page: Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");
}

test("clicking join more than 15 minutes before start shows a too-early pop-up", async ({ page, request }) => {
  const title = `Too Early E2E ${Date.now()}`;
  const starts = new Date(Date.now() + 2 * 60 * 60 * 1000);
  const ends = new Date(Date.now() + 3 * 60 * 60 * 1000);
  await loginAndCreateSession(page, request, title, starts, ends);

  await loginAsStudent(page);
  await page.goto("/it/student/course");
  const card = page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(card).toBeVisible();

  let dialogMessage = "";
  page.once("dialog", async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });
  await card.getByRole("button", { name: "Join class" }).click();
  await expect.poll(() => dialogMessage).toContain("Too early to join");
});

test("clicking join after the session has ended shows a completed pop-up", async ({ page, request }) => {
  const title = `Ended E2E ${Date.now()}`;
  const starts = new Date(Date.now() - 3 * 60 * 60 * 1000);
  const ends = new Date(Date.now() - 60 * 60 * 1000);
  await loginAndCreateSession(page, request, title, starts, ends);

  await loginAsStudent(page);
  await page.goto("/it/student/course");
  const card = page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(card).toBeVisible();

  let dialogMessage = "";
  page.once("dialog", async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });
  await card.getByRole("button", { name: "Join class" }).click();
  await expect.poll(() => dialogMessage).toContain("session has ended");
});

test("a joining student is asked to confirm their own identity before the real link opens", async ({ page, request }) => {
  const title = `Joinable E2E ${Date.now()}`;
  const starts = new Date(Date.now() - 5 * 60 * 1000);
  const ends = new Date(Date.now() + 60 * 60 * 1000);
  await loginAndCreateSession(page, request, title, starts, ends);

  await loginAsStudent(page);
  await page.goto("/it/student/course");
  const card = page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(card).toBeVisible();

  let dialogMessage = "";
  page.once("dialog", async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });
  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    card.getByRole("button", { name: "Join class" }).click(),
  ]);
  expect(dialogMessage).toMatch(/^Join as .+\(.+@.+\)\?$/);
  await popup.waitForLoadState();
  expect(popup.url()).toContain("e2e=join-button-check");
  await popup.close();
});
