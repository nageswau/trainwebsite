import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// hrc-009 (DEC-SCOPE-390): the primary recruiter changes a requirement's qualification; its open application is flagged "Needs review"
// (AC1, never rejected -- AC5), the collaborator gets one notice with the count (AC3), a description edit flags nothing (AC2), and the
// recruiter confirms the review from the review list. The section fits a phone.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function send(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const manager = await send(page, "/api/v1/admin/users", { role: "placement_manager", division: "global", full_name: `E2E H09 Manager ${stamp}`, email: `hrc009-m-${stamp}@example.local` });
  const recruiter = (suffix: string, name: string) => send(page, "/api/v1/admin/users", {
    role: "placement_team", full_name: `${name} ${stamp}`, email: `hrc009-${suffix}-${stamp}@example.local`,
    recruiter_profile: { employee_id: `H09-${stamp}-${suffix}`, reporting_manager_user_id: manager.id },
  });
  const primary = await recruiter("a", "E2E Primary");
  const mate = await recruiter("b", "E2E Mate");
  await page.request.post("/api/v1/auth/logout");
  for (const user of [primary, mate]) await activateWithToken(page.request, user.development_welcome_token);

  await signIn(page, "/it/login", primary.email);
  const company = await send(page, "/api/v1/recruiter/companies", { name: `E2E Hrc009 ${stamp} Labs` });
  const { requirement } = await send(page, "/api/v1/recruiter/requirements", {
    company_id: company.company.id, title: `Review Analyst ${stamp}`, location: "Pune", qualification: "B.Tech",
    required_skills: [`Py${stamp}`],
  });
  await send(page, `/api/v1/recruiter/requirements/${requirement.id}/assignments`, { user_id: mate.id, role: "collaborator" });
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const candidate = await send(page, "/api/v1/recruiter/candidates", { name: `E2E Flagged ${stamp}`, email: `hrc009-c-${stamp}@example.com`, source_id: sources.items[0].id });
  await send(page, `/api/v1/recruiter/requirements/${requirement.id}/candidates`, { candidate_id: candidate.id, status: "shortlisted" });
  return { primary, mate, requirement, candidateName: `E2E Flagged ${stamp}` };
}

async function edit(page: Page, label: string, value: string) {
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();
}

test("an eligibility change flags the open application, notifies the collaborator once, and is confirmed", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const { mate, requirement, candidateName } = await setUp(page, stamp);
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const section = page.getByRole("region", { name: /^Candidates/ });
  const row = section.getByRole("listitem", { name: candidateName });
  await expect(row).toBeVisible();

  // AC2: a description edit flags nothing
  await edit(page, "Job description", "Updated wording only");
  await expect(row.getByText("Needs review")).toHaveCount(0);

  // AC1 / AC5: the qualification changes; the application is flagged but stays Shortlisted
  await edit(page, "Qualification", "M.Tech");
  await expect(row.getByText("Needs review")).toBeVisible();
  await expect(row.getByText("Shortlisted", { exact: true })).toBeVisible();
  await expect(section.getByText("1 application needs review after an eligibility change. Confirm it or change its status.")).toBeVisible();

  // the review list, on a phone
  await page.setViewportSize({ width: 390, height: 844 });
  await section.getByRole("button", { name: "Show only these" }).click();
  await expect(section.getByRole("button", { name: "Show all candidates" })).toHaveAttribute("aria-pressed", "true");
  await expect(row).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await row.getByRole("button", { name: `Confirm review of ${candidateName}` }).click();
  await expect(section.getByText(`Review confirmed — ${candidateName} stays Shortlisted.`)).toBeVisible();
  await expect(section.getByText("No applications need review.")).toBeVisible();
  await section.getByRole("button", { name: "Show all candidates" }).click();
  await expect(row.getByText("Needs review")).toHaveCount(0);

  // AC3: the collaborator has exactly one notice, with the count and the link
  await signIn(page, "/it/login", mate.email);
  const inbox = await (await page.request.get("/api/v1/workflows/notifications")).json();
  const items = (Array.isArray(inbox) ? inbox : inbox.items) as { event_type: string | null; body: string; action_url: string | null }[];
  const notices = items.filter((n) => n.event_type === "it.requirement.review_needed");
  expect(notices).toHaveLength(1);
  expect(notices[0].body).toContain("Applications to review: 1.");
  expect(notices[0].action_url).toBe(`/recruiter/requirements/${requirement.id}`);
});
