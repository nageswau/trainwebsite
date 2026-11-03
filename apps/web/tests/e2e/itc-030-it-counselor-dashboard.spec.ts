import { expect, test, type Page } from "@playwright/test";

import { activateWithToken } from "./helpers/welcome";

// itc-030 (DEC-SCOPE-367): the IT counselor dashboard. A fresh IT counselor sees every widget at 0, then their walk-in lead and its
// follow-up (each figure equals its list, AC1); the Status filter narrows the lead widgets and lives in the address (AC2); a refused
// filter falls back to the whole board with the message; the IT Admin narrows every counselor's board by Owner; an overseas counselor is
// refused; the board fits a phone. Throwaway accounts (the shared stack DB is never clean).

const PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
  if (landing) await page.waitForURL(`**${landing}`);
}

const region = (page: Page, title: string, count: number) => page.getByRole("region", { name: new RegExp(`^${title} ${count}$`) });

test("an IT counselor's board counts their own work, filters by status, and the IT Admin narrows it by owner", async ({ page }) => {
  test.setTimeout(150_000);
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const stamp = Date.now();
  const password = `Itc030!${stamp}`;
  const name = `Itc030 Counselor ${stamp}`;
  const email = `itc030-c-${stamp}@example.local`;

  // Super Admin sets up a telecaller (and their manager) and a fresh IT counselor (the itc-011 world).
  await page.context().clearCookies();
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post("/api/v1/admin/users", { role: "telecaller_manager", division: "global", full_name: `Itc030 Manager ${stamp}`, email: `itc030-m-${stamp}@example.local` });
  const caller = await post("/api/v1/admin/users", {
    role: "telecaller", full_name: `Itc030 Telecaller ${stamp}`, email: `itc030-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `I30-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselor = await post("/api/v1/admin/users", { role: "counselor", division: "it", full_name: name, email });
  const course = await post("/api/v1/telecaller/products", { group: "it", name: `Itc030 Course ${stamp}` });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, counselor.development_welcome_token, password);
  await activateWithToken(page.request, caller.development_welcome_token, password);

  // A counselor with nothing: every widget is there, at 0 (E).
  await signIn(page, email, password, "/it/counselor/dashboard");
  for (const title of ["Follow-ups due today and overdue", "Ready to convert", "Students at risk", "Pending HR actions", "Assigned leads", "Conversions", "Enrolled students", "Outstanding fees", "Counseling pipeline"]) {
    await expect(region(page, title, 0)).toBeVisible();
  }
  await expect(page.getByText("Leads routed to you", { exact: true })).toBeVisible(); // tel-017's tiles stay

  // The telecaller hands them a lead; the counselor books a follow-up later today.
  await signIn(page, caller.email, password, "");
  const phone = `7${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const lead = await page.request.post("/api/v1/telecaller/leads", { data: { name: `Itc030 Lead ${stamp}`, email: `itc030-l-${stamp}@example.local`, phone, product_id: course.id, source: "walk_in" } });
  expect(lead.status(), await lead.text()).toBe(201);
  const leadId = (await lead.json()).id;
  const handed = await page.request.post(`/api/v1/telecaller/leads/${leadId}/handover`, { data: { counselor_id: counselor.id } });
  expect(handed.status(), await handed.text()).toBe(200);
  await signIn(page, email, password, "/it/counselor/dashboard");
  const fu = await page.request.post(`/api/v1/counselor/leads/${leadId}/follow-ups`, {
    data: { due_at: new Date(Date.now() + 2 * 60_000).toISOString(), reason: "counselor_call", next_action: "Call about the batch" },
  });
  expect(fu.status(), await fu.text()).toBe(201);

  await page.reload();
  const followUps = region(page, "Follow-ups due today and overdue", 1);
  await expect(followUps.getByText("Call about the batch")).toBeVisible();
  await expect(followUps.getByText("Overdue", { exact: true })).toHaveCount(0);
  await expect(region(page, "Assigned leads", 1).getByRole("link", { name: `Itc030 Lead ${stamp}` })).toBeVisible();
  await expect(region(page, "Counseling pipeline", 1)).toBeVisible();

  // AC2: Status narrows the lead widgets; the value is in the address and survives a reload.
  await page.getByLabel("Status").selectOption("qualified");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await page.waitForURL("**/it/counselor/dashboard?stage=qualified");
  await expect(region(page, "Assigned leads", 0)).toBeVisible();
  await expect(page.getByText("Status filters the lead widgets only: students have no lead status.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Status")).toHaveValue("qualified");
  await page.getByRole("link", { name: "Clear filters" }).click();
  await page.waitForURL(/\/it\/counselor\/dashboard$/);
  await expect(region(page, "Assigned leads", 1)).toBeVisible();

  // A refused filter: the whole board, with the message.
  await page.goto("/it/counselor/dashboard?program=not-a-course");
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Unknown filter value");
  await expect(region(page, "Assigned leads", 1)).toBeVisible();

  // The lead link opens the lead (where itc-011's Convert lives).
  await region(page, "Assigned leads", 1).getByRole("link", { name: `Itc030 Lead ${stamp}` }).click();
  await expect(page).toHaveURL(new RegExp(`/it/counselor/leads/${leadId}$`));

  // The IT Admin: Counselor Dashboard in the nav, narrowed to this counselor by Owner.
  await signIn(page, "itadmin@edusphere.local", PASSWORD, "/it/admin/dashboard");
  await page.getByRole("link", { name: "Counselor Dashboard" }).click();
  await page.waitForURL("**/it/admin/counselor-dashboard");
  await page.getByLabel("Owner").selectOption(counselor.id);
  await page.getByRole("button", { name: "Apply filters" }).click();
  await page.waitForURL(`**/it/admin/counselor-dashboard?owner=${counselor.id}`);
  await expect(region(page, "Assigned leads", 1).getByText(`Itc030 Lead ${stamp}`)).toBeVisible();
  expect(errors).toEqual([]);
});

test("an overseas counselor is refused the IT dashboard", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", "counselor@edusphere.local");
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/counselor/dashboard");
  const response = await page.request.get("/api/v1/counselor/it/dashboard");
  expect(response.status()).toBe(403);
});

test("the board fits a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "itadmin@edusphere.local", PASSWORD, "/it/admin/dashboard");
  await page.goto("/it/admin/counselor-dashboard");
  await expect(page.getByRole("region", { name: /^Assigned leads/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
