import { test, expect } from "@playwright/test";

// ADM-010 -- Agreement/consent oversight. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.
//
// Registers its own throwaway student rather than using the seeded
// `student.it@edusphere.local` account: `services/portal.py`'s consent-oversight query
// is capped and ordered by most-recently-created (RAID.md I-06/I-10 -- necessary because
// the shared dev DB has accumulated 5,000+ synthetic `it_student` rows, which defeats an
// alphabetical sort entirely), and the long-lived seeded demo account is now far too old
// to ever land inside that window. A freshly registered student always will.

async function loginAsItAdmin(page: import("@playwright/test").Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
}

test("IT Admin sees a freshly registered student's consent flip from 'Not yet' to 'Yes' after they accept (ADM-010-AC01)", async ({ page, request }) => {
  const unique = Date.now();
  const email = `adm010-${unique}@example.com`;
  const registered = await request.post("/api/v1/auth/register", {
    data: { email, password: "Sup3r-Secret-Pass!", full_name: `ADM-010 Student ${unique}`, division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();

  await request.post("/api/v1/auth/login", { data: { email, password: "Sup3r-Secret-Pass!", division: "it" } });
  const current = await (await request.get("/api/v1/workflows/it/student/agreements/current")).json();
  expect(current.id).toBeTruthy();
  expect(current.accepted).toBe(false);

  await loginAsItAdmin(page);
  await page.goto("/it/admin/consent");
  await expect(page.getByRole("heading", { name: "Agreement & Consent Oversight" })).toBeVisible();

  // The generic DataTable paginates client-side (RAID.md I-07) -- search to this run's
  // unique student rather than asserting on the raw unpaginated list.
  await page.getByLabel("Search records").fill(email);
  await expect(page.getByText("Not yet")).toBeVisible();

  const accept = await request.post(`/api/v1/workflows/it/student/agreements/${current.id}/accept`);
  expect(accept.ok()).toBeTruthy();

  await page.reload();
  await page.getByLabel("Search records").fill(email);
  await expect(page.getByText("Yes")).toBeVisible();
});

test("the consent oversight page requires authentication", async ({ page }) => {
  await page.goto("/it/admin/consent");
  await expect(page).toHaveURL(/\/it\/login/);
});
