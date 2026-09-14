import { test, expect } from "@playwright/test";

// TRN-003 -- Upcoming sessions and live-class join.
//
// Previously relied on the shared seeded "FastAPI APIs - Live Session" row, whose
// `starts_at` is fixed relative to whenever it was first seeded and is never refreshed
// by a later reseed -- documented as `RAID.md` I-10, and confirmed to have finally
// drifted into the past during this session (`starts_at` 2026-09-02, "now" 2026-09-09).
// Applies I-10's own recommended fix: creates its own throwaway upcoming session via the
// real API instead of depending on that fragile shared row.

test("trainer dashboard lists an upcoming session with a real join button (TRN-003-AC01)", async ({ page, request }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access")?.value;
  const context = await request.get("/api/v1/workflows/it/trainer/context", { headers: { cookie: `edusphere_access=${access}` } });
  const batchId = (await context.json()).batches[0]?.id;

  const title = `TRN-003 E2E Upcoming Session ${Date.now()}`;
  const starts = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  const ends = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();
  const created = await request.post("/api/v1/communications/it/live-sessions", {
    headers: { cookie: `edusphere_access=${access}` },
    data: { batch_id: batchId, title, starts_at: starts, ends_at: ends, provider: "manual", meeting_url: "https://meet.example.com/trn-003-e2e" },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/it/trainer/dashboard");
  await expect(page.getByRole("heading", { name: "Upcoming sessions" })).toBeVisible();
  const card = page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(card).toBeVisible();
  await expect(card.getByRole("button", { name: "Join class" })).toBeVisible();
});

test("upcoming sessions require authentication", async ({ page }) => {
  await page.goto("/it/trainer/dashboard");
  await expect(page).toHaveURL(/\/it\/login/);
});
