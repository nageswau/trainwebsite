import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-023 (DEC-SCOPE-109): a manager compares their two telecallers (one IT, one Overseas) for today -- leads received and a logged call --
// sorts, filters by team, follows a name to the daily activity, downloads the CSV and is refused a range over 366 days. Another manager's
// telecaller never appears. The IT admin sees IT telecallers only, without activity links; a telecaller is refused the page.

const IST_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" });
const istDay = (offsetDays: number) => IST_DAY.format(new Date(Date.now() + offsetDays * 86_400_000));
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function create(page: Page, data: Record<string, unknown>) {
  const response = await page.request.post("/api/v1/admin/users", { data });
  expect(response.status(), await response.text()).toBe(201);
  return { ...(await response.json()), full_name: data.full_name as string, email: data.email as string };
}

async function lead(page: Page, stamp: number, i: number, division = "it") {
  const created = await page.request.post("/api/v1/public/enquiries", {
    data: { division, name: `Perf Lead ${i} ${stamp}`, email: `tel023-${i}-${stamp}@example.com`, phone: `7${String(stamp).slice(-8)}${i}`, subject: "Python", message: "Call me." },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

async function setup(page: Page, stamp: number) {
  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await create(page, { role: "telecaller_manager", division: "global", full_name: `E2E Perf Manager ${stamp}`, email: `tel023-m-${stamp}@example.local` });
  const other = await create(page, { role: "telecaller_manager", division: "global", full_name: `E2E Perf Other ${stamp}`, email: `tel023-o-${stamp}@example.local` });
  const profile = (team: string, id: string, managerId: string) => ({ team, employee_id: `PF-${id}-${stamp}`, reporting_manager_user_id: managerId });
  const asha = await create(page, { role: "telecaller", full_name: `Asha Perf ${stamp}`, email: `tel023-a-${stamp}@example.local`, telecaller_profile: profile("it", "A", manager.id) });
  const bala = await create(page, { role: "telecaller", full_name: `Bala Perf ${stamp}`, email: `tel023-b-${stamp}@example.local`, telecaller_profile: profile("overseas", "B", manager.id) });
  const stranger = await create(page, { role: "telecaller", full_name: `Zed Perf ${stamp}`, email: `tel023-z-${stamp}@example.local`, telecaller_profile: profile("it", "Z", other.id) });
  const ashaLeads = [await lead(page, stamp, 0), await lead(page, stamp, 1)];
  const balaLead = await lead(page, stamp, 2, "overseas");
  for (const [ids, to] of [[ashaLeads, asha.id], [[balaLead], bala.id]] as const) {
    expect((await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: ids, telecaller_user_id: to } })).status()).toBe(200);
  }
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, asha]) await activateWithToken(page.request, user.development_welcome_token);
  // Asha logs one call today, signed in as herself.
  await page.request.post("/api/v1/auth/login", { data: { email: asha.email, password: E2E_PASSWORD, division: "it" } });
  expect((await page.request.post(`/api/v1/telecaller/leads/${ashaLeads[0]}/calls`, { data: { duration_seconds: 30, call_type: "outgoing", outcome: "interested" } })).status()).toBe(201);
  await page.request.post("/api/v1/auth/logout");
  return { manager, asha, bala, stranger };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const table = (page: Page) => page.getByRole("region", { name: "Performance by telecaller" }).getByRole("table");
const rowOf = (page: Page, name: string) => table(page).getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(name) }) });

test("a manager compares their telecallers; an IT admin sees IT only; a telecaller is refused", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const { manager, asha, bala, stranger } = await setup(page, stamp);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  const today = istDay(0);

  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/telecaller/manager/team");
  await page.getByRole("navigation").getByRole("link", { name: "Performance" }).click();
  await page.waitForURL("**/telecaller/manager/performance");
  await expect(page.getByRole("heading", { name: "Compare telecallers" })).toBeVisible();
  // Default: this month to today, Calls high-to-low -- Asha (1 call) above Bala; another manager's telecaller is never listed.
  await expect(page.getByLabel("To", { exact: true })).toHaveValue(today);
  const names = table(page).getByRole("rowheader");
  await expect(names).toHaveText([new RegExp(asha.full_name), new RegExp(bala.full_name), "Total"]);
  await expect(table(page)).not.toContainText(stranger.full_name);
  await expect(rowOf(page, asha.full_name).getByRole("cell")).toHaveText(["IT", "2", "1", "1", "0", "0", "0"]);
  await expect(rowOf(page, bala.full_name).getByRole("cell")).toHaveText(["Overseas", "1", "0", "0", "0", "0", "0"]);
  await expect(rowOf(page, "Total").getByRole("cell")).toHaveText(["", "3", "1", "1", "0", "0", "0"]);

  // Sort by name (A-Z), then team filter narrows to Overseas; the sort is kept.
  await table(page).getByRole("link", { name: /^Telecaller: sort/ }).click();
  await expect(page).toHaveURL(/sort=name&dir=asc/);
  await expect(table(page).getByRole("columnheader", { name: /Telecaller/ })).toHaveAttribute("aria-sort", "ascending");
  await page.getByLabel("Team", { exact: true }).selectOption("overseas");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/team=overseas.*sort=name/);
  await expect(names).toHaveText([new RegExp(bala.full_name), "Total"]);

  // CSV = the screen.
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^telecaller-performance-\d{4}-\d{2}-\d{2}-to-\d{4}-\d{2}-\d{2}\.csv$/);
  await expect(page.getByText("Report downloaded.")).toBeVisible();

  // A range over 366 days is refused with the API's sentence; the form keeps the entered dates.
  await page.goto(`/telecaller/manager/performance?date_from=${istDay(-400)}&date_to=${today}`);
  await expect(page.getByRole("region", { name: "Telecaller performance" }).getByRole("alert")).toHaveText("The range can't be longer than 366 days");
  await expect(page.getByLabel("From", { exact: true })).toHaveValue(istDay(-400));

  // A name opens that telecaller's daily activity for the range's last day.
  await page.goto("/telecaller/manager/performance");
  await table(page).getByRole("link", { name: asha.full_name }).click();
  await page.waitForURL(`**/telecaller/manager/team/${asha.id}/activity?date=${today}`);
  await expect(page.getByRole("heading", { name: asha.full_name })).toBeVisible();

  // Phone width: the table scrolls inside its region, the page does not.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/telecaller/manager/performance");
  await expect(table(page)).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // The IT admin: IT telecallers only, plain names, no team picker.
  await signIn(page, "it", "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");
  await page.goto("/it/admin/telecaller-performance");
  await expect(rowOf(page, asha.full_name)).toBeVisible();
  await expect(table(page)).not.toContainText(bala.full_name);
  await expect(table(page).getByRole("link", { name: asha.full_name })).toHaveCount(0);
  await expect(page.getByLabel("Team", { exact: true })).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  // A telecaller is refused, on the page and on the API.
  await signIn(page, "it", asha.email, E2E_PASSWORD, "/telecaller/dashboard");
  await page.goto("/telecaller/manager/performance");
  await expect(page.getByText("Telecaller Manager role required")).toBeVisible();
  expect((await page.request.get("/api/v1/telecaller/manager/performance")).status()).toBe(403);

  expect(errors).toEqual([]);
});
