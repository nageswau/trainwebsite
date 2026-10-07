import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-019 (DEC-SCOPE-097): an IT telecaller files a school meeting request for the school BDMs' pool; a school BDM finds it on My Day,
// accepts it into a bdm-006 appointment (AC2) and the telecaller sees it Accepted. A corporate request goes to the college BDMs (AC1) and
// is declined with a reason (AC3). Throwaway accounts; phone width has no sideways scroll.
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "overseas" | "admin", email: string, password: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function accounts(page: Page, stamp: number) {
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const tlManager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E MR TL Manager ${stamp}`, email: `tel019-tm-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E MR Telecaller ${stamp}`, email: `tel019-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `MR-${stamp}`, reporting_manager_user_id: tlManager.id },
  });
  const bdmManager = await post({ role: "bdm_manager", division: "global", full_name: `E2E MR BDM Manager ${stamp}`, email: `tel019-bm-${stamp}@example.local` });
  const bdm = (type: string) => post({
    role: "bdm", full_name: `E2E MR ${type} BDM ${stamp}`, email: `tel019-${type}-${stamp}@example.local`,
    bdm_profile: { bdm_type: type, employee_id: `MR${type.slice(0, 1).toUpperCase()}-${stamp}`, reporting_manager_user_id: bdmManager.id },
  });
  const school = await bdm("school");
  const college = await bdm("college");
  await page.request.post("/api/v1/auth/logout");
  for (const user of [caller, school, college]) await activateWithToken(page.request, user.development_welcome_token);
  return { caller, school, college };
}

// The day after tomorrow at 11:00 India time, as a datetime-local value.
const at11 = (days: number) => `${new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + days * 86_400_000))}T11:00`;
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function fileRequest(page: Page, type: string, org: string, purpose: string) {
  await page.goto("/telecaller/meeting-requests/new");
  const form = page.getByRole("form", { name: "Request a BDM meeting" });
  await form.getByLabel("Meeting type").selectOption({ label: type });
  await form.getByLabel("Organization").fill(org);
  await form.getByLabel("Person to meet").fill("Ms Iyer");
  await form.getByLabel("Phone").fill("+91 98765 43210");
  await form.getByLabel("Proposed date and time (IST)").fill(at11(2));
  await form.getByLabel("Purpose").fill(purpose);
  await form.getByRole("button", { name: "Send request" }).click();
  await page.waitForURL(/\/telecaller\/meeting-requests\?filed=MRQ-\d{6}$/);
  return new URL(page.url()).searchParams.get("filed") as string;
}

test("a school request is accepted into an appointment; a corporate request is declined with a reason", async ({ page }) => {
  const stamp = Date.now();
  const { caller, school, college } = await accounts(page, stamp);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // --- the telecaller files two requests -------------------------------------------------------------------------------------------
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  await page.getByRole("link", { name: "BDM requests" }).first().click();
  await expect(page.getByText("No meeting requests yet.")).toBeVisible();
  await page.getByRole("link", { name: "New request" }).click();
  const form = page.getByRole("form", { name: "Request a BDM meeting" });
  await form.getByRole("button", { name: "Send request" }).click(); // refused in place, the first field focused
  await expect(form.getByText("Choose the meeting type.")).toBeVisible();
  await expect(form.getByLabel("Meeting type")).toBeFocused();
  await form.getByLabel("Meeting type").selectOption({ label: "Corporate meeting" });
  await expect(form.getByLabel("BDM").locator("option").first()).toHaveText("Any College BDM"); // T26

  const schoolOrg = `St Mary ${stamp}`;
  const schoolCode = await fileRequest(page, "School meeting", schoolOrg, "Career guidance talk for grade 12");
  await expect(page.getByText(`Request ${schoolCode} sent.`)).toBeVisible();
  const corporateCode = await fileRequest(page, "Corporate meeting", `Infosys ${stamp}`, "Campus hiring tie-up");
  const row = (code: string) => page.getByRole("row").filter({ hasText: code });
  await expect(row(schoolCode).getByText("Pending", { exact: true })).toBeVisible();
  await expect(row(schoolCode).getByText("Any School BDM")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // --- the school BDM: My Day -> accept into an appointment -------------------------------------------------------------------------
  await signIn(page, "overseas", school.email, E2E_PASSWORD, "/bdm/my-day");
  const org = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "school", name: schoolOrg, city: "Kochi", contacts: [{ name: "Ms Iyer", designation: "Principal", role: "principal" }] },
  });
  expect(org.status(), await org.text()).toBe(201);
  await page.reload();
  const card = page.getByRole("region", { name: "Meeting requests" });
  await card.getByRole("link", { name: schoolCode }).click();
  await expect(page.getByRole("heading", { name: new RegExp(schoolCode) })).toBeVisible();
  await expect(page.getByText("Career guidance talk for grade 12").first()).toBeVisible();
  await expect(page.getByLabel("Type (required)")).toHaveValue("school_meeting"); // MR9: started from the request
  await expect(page.getByLabel("Date and time (IST) (required)")).toHaveValue(at11(2));
  const picker = page.getByLabel("Organization (required)");
  await picker.fill(schoolOrg);
  await page.getByRole("option", { name: new RegExp(schoolOrg) }).first().click();
  await expect(page.getByLabel(/Contact person/)).not.toHaveValue("");
  await page.getByRole("button", { name: "Accept and book" }).click();
  await page.waitForURL(/\/bdm\/appointments\/[0-9a-f-]{36}\?created=1$/);
  const apptCode = (await page.getByText(/APT-\d{6}/).first().textContent())?.match(/APT-\d{6}/)?.[0] as string;
  expect(apptCode).toMatch(/^APT-\d{6}$/);
  await page.goto("/bdm/meeting-requests?status=accepted");
  await expect(row(schoolCode).getByRole("link", { name: apptCode })).toBeVisible();
  // AC1: the corporate request is not in a school BDM's inbox
  await page.goto("/bdm/meeting-requests?status=all");
  await expect(row(corporateCode)).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  // --- the college BDM declines the corporate request (AC3) -------------------------------------------------------------------------
  await signIn(page, "it", college.email, E2E_PASSWORD, "/bdm/my-day");
  await page.getByRole("link", { name: "Requests" }).first().click();
  await row(corporateCode).getByRole("link", { name: corporateCode }).click();
  await page.getByRole("button", { name: "Decline request" }).click();
  await expect(page.getByText("Enter the reason for declining.")).toBeVisible();
  await page.getByLabel("Reason for declining").fill("Corporate tie-ups paused this quarter");
  await page.getByRole("button", { name: "Decline request" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(corporateCode) }).getByText("Declined")).toBeVisible();
  await expect(page.getByRole("button", { name: "Decline request" })).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  // --- the telecaller sees both outcomes ----------------------------------------------------------------------------------------------
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  await page.goto("/telecaller/meeting-requests");
  await expect(row(schoolCode).getByText("Accepted", { exact: true })).toBeVisible();
  await expect(row(schoolCode).getByText(apptCode)).toBeVisible();
  await expect(row(corporateCode).getByText("Declined", { exact: true })).toBeVisible();
  await expect(row(corporateCode).getByText("Reason: Corporate tie-ups paused this quarter")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
