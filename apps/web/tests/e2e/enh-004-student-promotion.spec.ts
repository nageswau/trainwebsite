import { test, expect, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-004 -- student promotion. Requires the stack running via `docker compose up` with
// `python -m app.seed` applied (seeds overseasadmin@edusphere.local/Demo@123). Builds two throwaway
// schools; the second exists only to prove a coordinator cannot promote another school's student.
//
// Shared-state note: promotion needs an ACTIVE academic year the students are not already in, and a
// year cannot be deleted through the API. So each run closes any earlier `e2e4-*` year, then creates and
// activates a far-future one (it wins the "latest start_date" tie-break over the real year) AFTER the
// roster exists. The only lasting effect is that students later created by other specs get that year.

const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";
const PARENT_PASSWORD = "Sup3r-Secret-Pass!";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function createSchool(page: Page, unique: number, tag: string) {
  const coordinatorEmail = `enh004-e2e-${tag}-${unique}@example.local`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-004 School ${tag} ${unique}`);
  await page.fill("#school-coordinator-name", `E2E ENH-004 Coordinator ${tag}`);
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  return coordinatorEmail;
}

async function createStudent(page: Page, data: Record<string, unknown>) {
  const response = await page.request.post("/api/v1/school/students", { data });
  expect(response.status()).toBe(201);
  return response.json();
}

const studentRow = (page: Page, name: string) => page.getByRole("listitem").filter({ hasText: name });

test("coordinator promotes and holds back students; the parent sees the new grade; history is kept; another school is refused (ENH-004)", async ({ page }) => {
  test.setTimeout(90_000);
  const unique = Date.now();
  const parentEmail = `enh004-e2e-parent-${unique}@example.local`;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const coordinatorA = await createSchool(page, unique, "a");
  const coordinatorB = await createSchool(page, unique, "b");

  // School A's roster is created while the previous academic year is still the active one.
  await signIn(page, coordinatorA, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const alpha = await createStudent(page, { full_name: "E2E Promo Alpha", grade_or_class: "Grade 8-A", grade_level: 8, parent_name: "E2E Promo Parent", parent_email: parentEmail });
  await createStudent(page, { full_name: "E2E Promo Beta", grade_or_class: "Grade 8-B", grade_level: 8 });
  await createStudent(page, { full_name: "E2E Promo Twelve", grade_or_class: "Grade 12", grade_level: 12 });
  const parentToken = alpha.development_invite_token;
  expect(parentToken).toBeTruthy();

  // A new academic year becomes active. Earlier runs' `e2e4-*` years are closed first, so exactly one e2e year is
  // active (start dates are day-granular, so a "later date" trick would tie for two runs on the same day). The far
  // future start date only makes it win over the real, seeded year; real years are never touched.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const years: { id: string; label: string; status: string }[] = await (await page.request.get("/api/v1/overseas-admin/academic-years")).json();
  for (const old of years.filter((y) => y.label.startsWith("e2e4-") && y.status === "active")) {
    expect((await page.request.patch(`/api/v1/overseas-admin/academic-years/${old.id}`, { data: { status: "closed" } })).ok()).toBeTruthy();
  }
  const yearLabel = `e2e4-${unique}`;
  const created = await page.request.post("/api/v1/overseas-admin/academic-years", {
    data: { label: yearLabel, start_date: "5000-01-01", end_date: "5000-12-31" },
  });
  expect(created.status()).toBe(201);
  const activated = await page.request.patch(`/api/v1/overseas-admin/academic-years/${(await created.json()).id}`, { data: { status: "active" } });
  expect(activated.ok()).toBeTruthy();

  // Another school's coordinator cannot touch school A's student (AC-04).
  await signIn(page, coordinatorB, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const foreign = await page.request.post("/api/v1/school/students/promotions", { data: { items: [{ student_id: alpha.id, action: "promote" }] } });
  expect(foreign.status()).toBe(403);

  // School A's coordinator promotes Alpha, holds Beta back, and tries the Grade 12 student.
  await signIn(page, coordinatorA, E2E_PASSWORD, "**/school/coordinator/dashboard");
  await page.goto("/school/coordinator/promotion");
  await expect(page.getByText(yearLabel).first()).toBeVisible();
  await page.getByRole("checkbox", { name: /E2E Promo Alpha/ }).check();
  await page.getByRole("checkbox", { name: /E2E Promo Beta/ }).check();
  await studentRow(page, "E2E Promo Beta").getByLabel("Action").selectOption("hold_back");
  await page.getByRole("checkbox", { name: /E2E Promo Twelve/ }).check();
  // The Grade 12 student is flagged before anything is submitted (advisory; the server decides).
  await expect(studentRow(page, "E2E Promo Twelve")).toContainText("Grade 12 is the highest grade");

  // High-consequence action: an explicit confirmation step, not a one-click apply.
  await page.getByRole("button", { name: /Review changes \(3\)/ }).click();
  await expect(page.getByText(`Promote 2 and hold back 1 into ${yearLabel}?`)).toBeVisible();
  await page.getByRole("button", { name: "Confirm promotion" }).click();
  await expect(page.getByText(`Done for ${yearLabel}: 1 promoted, 1 held back, 1 not changed, 0 skipped.`)).toBeVisible();

  // The server's per-row outcome is shown at once, before any reload.
  await expect(studentRow(page, "E2E Promo Alpha")).toContainText("Grade 9-A");
  await expect(studentRow(page, "E2E Promo Alpha")).toContainText("Promoted");
  await expect(studentRow(page, "E2E Promo Beta")).toContainText("Held back");
  await expect(studentRow(page, "E2E Promo Twelve")).toContainText("Not changed");

  // ...and it survives a full reload: processed students are locked, the failed one is not.
  await page.reload();
  await expect(studentRow(page, "E2E Promo Alpha")).toContainText(`Already in ${yearLabel}`);
  await expect(studentRow(page, "E2E Promo Beta")).toContainText(`Already in ${yearLabel}`);
  await expect(studentRow(page, "E2E Promo Twelve")).not.toContainText("Already in");
  await page.selectOption("#promotion-filter", "12");
  await expect(page.getByRole("listitem").filter({ hasText: "E2E Promo" })).toHaveCount(1);

  // Keyboard: Space toggles the checkbox; Enter opens the confirm step and moves focus to it; Escape backs out and returns focus.
  const twelveBox = page.getByRole("checkbox", { name: /E2E Promo Twelve/ });
  await twelveBox.focus();
  await page.keyboard.press("Space");
  await expect(twelveBox).toBeChecked();
  const review = page.getByRole("button", { name: /Review changes \(1\)/ });
  await review.press("Enter");
  await expect(page.getByRole("button", { name: "Confirm promotion" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(review).toBeFocused();

  // Responsive (RESPONSIVE_RULES): no horizontal scroll at 320 / 768 / 1024 / 1440, and the primary action stays reachable.
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `horizontal overflow at ${width}px` }).toBe(true);
    await expect(review).toBeInViewport();
  }
  await page.setViewportSize({ width: 1280, height: 720 });

  // The Parent (invited earlier, accepting now) sees the promoted grade on the dashboard.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", PARENT_PASSWORD);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await expect(page.getByRole("heading", { name: "E2E Promo Alpha" })).toBeVisible();
  await expect(page.getByText("Grade 9-A").first()).toBeVisible();

  // The child page keeps the prior grade: a "Promoted" entry from Grade 8-A to Grade 9-A in the new year (AC-02).
  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${alpha.id}`);
  await expect(page.getByRole("heading", { name: "Grade history" })).toBeVisible();
  await expect(page.getByText("Moved from Grade 8-A to Grade 9-A")).toBeVisible();
  // The students were created inside the previously active year, so the entry reads "<previous year> to <new year>".
  await expect(page.getByText(new RegExp(`Academic year: .*${yearLabel}`))).toBeVisible();

  // The coordinator's student page shows the held-back outcome, and the empty state for an unpromoted student.
  await signIn(page, coordinatorA, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const students = await (await page.request.get("/api/v1/school/students")).json();
  const beta = students.find((s: { full_name: string }) => s.full_name === "E2E Promo Beta");
  const twelve = students.find((s: { full_name: string }) => s.full_name === "E2E Promo Twelve");
  await page.goto(`/school/coordinator/students/${beta.id}`);
  await expect(page.getByRole("heading", { name: "Grade history" })).toBeVisible();
  await expect(page.getByText("Kept in Grade 8-B")).toBeVisible();
  await page.goto(`/school/coordinator/students/${twelve.id}`);
  await expect(page.getByText("No promotions recorded yet.")).toBeVisible();
});
