import { test, expect } from "@playwright/test";

// AUTH-002 -- Role-based access control enforcement (UI). Requires the stack running
// via `docker compose up` with `python -m app.seed` already applied.

test("public header shows Login when signed out (AUTH-002-AC01)", async ({ page }) => {
  await page.goto("/it");
  await expect(page.getByRole("link", { name: "Login" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
});

test("public header shows role-appropriate Dashboard + Logout once signed in, and Logout actually ends the session (AUTH-002-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it");
  const dashboardLink = page.getByRole("link", { name: "Dashboard" });
  await expect(dashboardLink).toBeVisible();
  await expect(dashboardLink).toHaveAttribute("href", "/it/student/dashboard");
  await expect(page.getByRole("link", { name: "Login" })).toHaveCount(0);

  await page.getByRole("button", { name: "Logout" }).click();
  await page.waitForURL("**/", { timeout: 10000 });
  await expect(page.getByRole("link", { name: "Login" })).toBeVisible();

  // Logout must be real, not just a UI flip -- the session cookie should actually be gone.
  await page.goto("/it/student/dashboard");
  await expect(page).toHaveURL(/\/it\/login/);
});

test("a role-mismatched dashboard URL is blocked server-side, never renders the other role's content (AUTH-002-AC02)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  // A student's session hitting the IT Admin workspace directly by URL.
  const response = await page.goto("/it/admin/dashboard");
  // Server Component: the block happens before any HTML is sent, so the *initial*
  // response body itself must never contain admin-only content -- not just the final
  // DOM state, which would also pass if it rendered-then-redirected client-side.
  const body = (await response?.body())?.toString() ?? "";
  expect(body).not.toContain("IT Administrator");
  await expect(page.getByText("Access unavailable")).toBeVisible();
});

test("the mismatched role/division check is enforced at the API layer independent of the UI (AUTH-002-AC03)", async ({ request, page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access");
  const crossRole = await request.get("/api/v1/portal/it/admin/dashboard", {
    headers: { cookie: `edusphere_access=${access?.value}` },
  });
  expect(crossRole.status()).toBe(403);

  const ownRole = await request.get("/api/v1/portal/it/student/dashboard", {
    headers: { cookie: `edusphere_access=${access?.value}` },
  });
  expect(ownRole.status()).toBe(200);
});
