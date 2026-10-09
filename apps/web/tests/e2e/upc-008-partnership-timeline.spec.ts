import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-008 (AC1, P1, E2, X1): the owner records the §5 expected timeline (month and quarter derived, Q-10); a milestone past its target
// and not achieved shows as Delayed (AC1) and stops being delayed once achieved; a move into Proposal Sent auto-completes Proposal (MS4);
// the head edits too; a future achieved date is refused by the field; the section fits a phone. Throwaway accounts via the real admin API.

const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, loginPath: string, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function setUp(page: Page, stamp: number) {
  await superAdmin(page);
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc008-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc008-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U08-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Timeline University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, university };
}

test("expected timeline, delayed milestones, auto Proposal and the head's edit", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { head, manager, university } = await setUp(page, stamp);

  await signIn(page, "/overseas/login", manager.email, "/partnership/dashboard");
  await page.goto(`/partnership/universities/${university.id}`);
  const section = page.getByRole("region", { name: "Partnership timeline" });
  const expected = section.getByRole("group", { name: "Expected timeline" });
  await expect(expected.getByText("Not set")).toHaveCount(6);

  // X1 / Q-10: the owner records the targets; month and quarter follow the target partnership date.
  await section.getByRole("button", { name: "Edit expected timeline" }).click();
  await section.getByLabel("Target partnership date").fill("2026-11-15");
  await section.getByLabel("Expected intake").fill("January 2027");
  await section.getByRole("button", { name: "Save expected timeline" }).click();
  await expect(section.getByRole("status")).toHaveText("Expected timeline saved.");
  await expect(expected.getByText("November 2026")).toBeVisible();
  await expect(expected.getByText("Q4 2026 (Oct–Dec)")).toBeVisible();
  await expect(expected.getByText("January 2027")).toBeVisible();

  // AC1: Meeting past its target and not achieved is Delayed (row highlighted, summary line); achieving it clears that.
  const table = section.getByRole("table", { name: "Partnership milestones" });
  await expect(table.getByRole("row")).toHaveCount(14);
  await section.getByRole("button", { name: "Edit Meeting" }).click();
  await section.getByLabel("Target date").fill(inDays(-2));
  await section.getByRole("button", { name: "Save", exact: true }).click();
  await expect(section.getByRole("status")).toHaveText("Meeting saved.");
  const meeting = table.getByRole("row", { name: /^Meeting/ });
  await expect(meeting.getByText("Delayed")).toBeVisible();
  await expect(meeting).toHaveClass(/milestone-delayed/);
  await expect(section.getByText("1 milestone delayed")).toBeVisible();
  await expect(section.getByRole("button", { name: "Edit Meeting" })).toBeFocused();

  // N1: the browser refuses a future achieved date on the field itself (max = today, IST); the API's 422 is the backstop.
  await section.getByRole("button", { name: "Edit Meeting" }).click();
  await section.getByLabel("Achieved on").fill(inDays(2));
  await section.getByRole("button", { name: "Save", exact: true }).click();
  await expect(section.getByRole("form", { name: "Edit Meeting" })).toBeVisible();
  expect(await section.getByLabel("Achieved on").evaluate((el: HTMLInputElement) => el.validity.rangeOverflow)).toBe(true);
  await section.getByLabel("Achieved on").fill(inDays(0));
  await section.getByRole("button", { name: "Save", exact: true }).click();
  await expect(meeting.getByText("Done")).toBeVisible();
  await expect(section.getByText("1 milestone delayed")).toHaveCount(0);

  // MS4: a move into Proposal Sent auto-completes Proposal (the section remounts with the page).
  await page.getByLabel("Move to").selectOption("proposal_sent");
  await page.getByRole("button", { name: "Move" }).click();
  const proposal = table.getByRole("row", { name: /^Proposal/ });
  await expect(proposal.getByText("(Auto, from the stage move)")).toBeVisible();
  await expect(proposal.getByText("Done")).toBeVisible();

  // The head edits their manager's university too.
  await signIn(page, "/admin/login", head.email, "/partnership/head/team");
  await page.goto(`/partnership/universities/${university.id}`);
  await section.getByRole("button", { name: "Edit Presentation" }).click();
  await section.getByLabel("Target date").fill(inDays(10));
  await section.getByRole("button", { name: "Save", exact: true }).click();
  await expect(section.getByRole("status")).toHaveText("Presentation saved.");

  // Phone: the page does not scroll sideways (the table scrolls inside its own box).
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(section.getByRole("table", { name: "Partnership milestones" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
