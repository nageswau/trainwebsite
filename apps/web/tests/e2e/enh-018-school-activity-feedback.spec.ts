import { expect, test, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-018 -- a coordinator gives feedback on a completed Edusphere activity using only the keyboard (at phone width), the principal
// reads it without being able to submit, an admin reads it across schools, and a second submission is refused. Requires the stack
// running with `python -m app.seed` applied (seeds overseasadmin@edusphere.local/Demo@123). Builds a throwaway school per run.
const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

test("coordinator gives feedback by keyboard; principal and admin read it; a duplicate is refused (ENH-018)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(`${new URL(page.url()).pathname}: ${String(error).slice(0, 140)}`));

  // An admin creates the school and its coordinator.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const coordinatorEmail = `enh018-e2e-coord-${unique}@example.local`;
  const schoolName = `E2E ENH-018 School ${unique}`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E ENH-018 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum"); // ENH-022: scheduling an activity needs a valid partnership tier
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");

  // The coordinator has a career seminar that took place an hour ago, and invites a principal.
  await signIn(page, coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const title = `E2E Career Seminar ${unique}`;
  const created = await page.request.post("/api/v1/school/activities", { data: { title, scheduled_at: new Date(Date.now() - 3_600_000).toISOString(), activity_type: "career_seminar" } });
  expect(created.status()).toBe(201);
  const activity = await created.json();
  const invited = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_principal", full_name: "E2E ENH-018 Principal", email: `enh018-e2e-principal-${unique}@example.local` } });
  expect(invited.status()).toBe(201);
  const { development_invite_token: principalToken } = await invited.json();

  // From the Activities list straight to this activity's feedback form (QA-018-09), keyboard only, at phone width.
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/school/coordinator/activities");
  await page.getByRole("link", { name: `Give feedback for ${title}` }).click();
  await page.waitForURL(`**/school/coordinator/feedback?activity=${activity.id}`);
  await expect(page.getByRole("link", { name: "Show all activities" })).toBeVisible();
  await expect(page.getByRole("heading", { name: `Feedback: ${title}` })).toBeFocused();
  await page.keyboard.press("Tab"); // Overall rating group
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight"); // 4 – Very good
  await page.keyboard.press("Tab"); // School satisfaction group
  for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight"); // 5 – Excellent
  await page.keyboard.press("Tab");
  await page.keyboard.type("Ms. Rao");
  await page.keyboard.press("Tab");
  const longWord = "Excellent".repeat(40);
  await page.keyboard.type(`Students were engaged. ${longWord}`);
  await page.keyboard.press("Tab");
  await page.keyboard.type("More time for questions.");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.getByText(`Feedback saved for ${title}.`)).toBeVisible();
  // The focused activity's saved feedback is shown expanded straight away.
  await expect(page.getByText("4 – Very good")).toBeVisible();
  await expect(page.getByText("5 – Excellent")).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: "long feedback text overflows at 320px" }).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // A direct (server-rendered) load of the Feedback page hydrates cleanly and shows the stored feedback.
  await page.goto("/school/coordinator/feedback");
  await expect(page.getByRole("list", { name: "Completed Edusphere activities" }).getByText("Submitted", { exact: true })).toBeVisible();

  // The Activities list now offers View feedback for it (QA-018-10).
  await page.goto("/school/coordinator/activities");
  await expect(page.getByRole("link", { name: `View feedback for ${title}` })).toBeVisible();
  await expect(page.getByRole("link", { name: `Give feedback for ${title}` })).toHaveCount(0);

  // A second submission (a retry, or another tab) is refused and the stored feedback is unchanged.
  const duplicate = await page.request.post(`/api/v1/school/activities/${activity.id}/feedback`, { data: { rating: 1, satisfaction: 1, feedback: "again" } });
  expect(duplicate.status()).toBe(409);

  // The principal reads it and cannot submit.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${principalToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");
  await page.getByRole("link", { name: "Feedback" }).first().click();
  await page.waitForURL("**/school/principal/feedback");
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByRole("list", { name: "Completed Edusphere activities" }).getByText("Submitted", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Give feedback/ })).toHaveCount(0);
  // ...and is refused on the coordinator's page rather than shown a form it cannot submit (QA-018-12).
  await page.goto("/school/coordinator/feedback");
  await expect(page.getByText("School Coordinator role required")).toBeVisible();

  // Edusphere management reads it across schools, filtered to this one.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/activity-feedback");
  await expect(page.getByRole("option", { name: schoolName })).toBeAttached();
  await page.getByLabel("Search schools").fill(schoolName); // QA-018-16: narrow the long list first, as an admin would
  await page.getByLabel("School", { exact: true }).selectOption({ label: schoolName });
  const card = page.getByRole("listitem").filter({ hasText: title });
  await expect(card.getByText("Ms. Rao")).toBeVisible();
  await expect(card.getByText("5 – Excellent")).toBeVisible();
  await expect(card.getByText(schoolName)).toBeVisible();

  expect(pageErrors).toEqual([]);
});
