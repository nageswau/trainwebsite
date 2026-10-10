import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-027 (AC1-AC4, OB3, OB11): before signing, the university page says onboarding waits for a signed agreement. Once an MoU is signed
// (set up through the real API), the manager sees the ten §29 items as Not Started, edits one (status, owner, note), and completing the
// last item moves the university to Partner Activated. An overseas_admin reads the checklist without Edit; the page fits a phone.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
const ITEMS = [
  "counselor_training", "application_team_training", "product_training", "university_portal_access", "application_process",
  "marketing_material", "course_database_updated", "commission_setup", "university_contact_setup", "first_student_campaign",
];

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function apiLogin(request: APIRequestContext, email: string, division = "overseas") {
  await request.post("/api/v1/auth/logout");
  const response = await request.post("/api/v1/auth/login", { data: { email, password: E2E_PASSWORD, division } });
  expect(response.ok(), await response.text()).toBe(true);
}

async function send(request: APIRequestContext, method: "post" | "patch", url: string, data: unknown) {
  const response = await request[method](url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const post = (url: string, data: unknown) => send(page.request, "post", url, data);
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc027-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc027-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U27-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc027-a-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Onboarding University ${stamp}`, country_id: countries.items[0].id, city: "Leeds" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { head, manager, admin, university };
}

/** The upc-014 flow through the API: draft, send, review, the head approves, the manager uploads the MoU, records the signatures, signs. */
async function signAgreement(request: APIRequestContext, universityId: string, head: { email: string }, manager: { id: string; email: string }) {
  await apiLogin(request, manager.email);
  let { agreement } = await send(request, "post", `/api/v1/partnership/universities/${universityId}/agreements`,
    { agreement_type: "mou", start_date: day(-30), expiry_date: day(700), exclusivity: "exclusive" });
  const move = async (to: string) => ({ agreement } = await send(request, "post", `/api/v1/partnership/agreements/${agreement.id}/status`, { from_status: agreement.status, to_status: to }));
  await move("sent");
  await move("under_review");
  await apiLogin(request, head.email, "global");
  await move("approved");
  await apiLogin(request, manager.email);
  const upload = await request.post(`/api/v1/partnership/universities/${universityId}/documents`, {
    multipart: { kind: "mou", title: "Signed MoU", file: { name: "mou.pdf", mimeType: "application/pdf", buffer: PDF } },
  });
  expect(upload.ok(), await upload.text()).toBe(true);
  const { document } = await upload.json();
  ({ agreement } = await send(request, "patch", `/api/v1/partnership/agreements/${agreement.id}`, {
    document_id: document.id, edusphere_signatory_user_id: manager.id, edusphere_signed_on: day(-1),
    university_signatory_name: "Prof. A. Registrar", university_signed_on: day(-2),
  }));
  await move("signed");
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("a signed university's onboarding is tracked and completing it activates the partner", async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const { head, manager, admin, university } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;
  const section = page.locator(`section[aria-labelledby="onboarding-${university.id}-heading"]`);
  const status = section.locator("p[role=status]");

  // OB3: before signing it only says so.
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  await expect(section.getByRole("heading", { name: "Partner onboarding" })).toBeVisible();
  await expect(section.getByText("Onboarding starts when an agreement is signed.")).toBeVisible();
  await expect(section.getByRole("table")).toHaveCount(0);

  // AC1: signing shows the ten items as Not Started.
  await signAgreement(page.request, university.id, head, manager);
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  const table = section.getByRole("table", { name: "Partner onboarding checklist" });
  await expect(table.getByRole("row")).toHaveCount(11);
  await expect(section.getByText(/0 of 10 completed/)).toBeVisible();
  await expect(table.getByRole("rowheader", { name: "Counselor training" })).toBeVisible();
  await expect(table.getByText("Not Started")).toHaveCount(10);

  // AC3: one item's status, owner and note.
  await section.getByRole("button", { name: "Edit Counselor training" }).click();
  const form = section.getByRole("form", { name: "Edit Counselor training" });
  await form.getByLabel("Status").selectOption("in_progress");
  await form.getByRole("combobox", { name: "Owner" }).fill(manager.email);
  await page.getByRole("option", { name: new RegExp(`E2E Manager ${stamp}`) }).click();
  await form.getByLabel("Note").fill("Batch 1 booked for Monday");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(status).toHaveText("Counselor training saved.");
  const row = table.getByRole("row", { name: /Counselor training/ });
  await expect(row.getByText("In Progress")).toBeVisible();
  await expect(row.getByText(`E2E Manager ${stamp}`)).toBeVisible();
  await expect(row.getByText("Batch 1 booked for Monday")).toBeVisible();
  await page.reload();
  await expect(table.getByRole("row", { name: /Counselor training/ }).getByText("In Progress")).toBeVisible(); // persisted

  // AC4: nine items completed through the API, the last one on the page -> Partner Activated.
  await apiLogin(page.request, manager.email);
  for (const kind of ITEMS.slice(0, -1)) await send(page.request, "patch", `/api/v1/partnership/universities/${university.id}/onboarding/${kind}`, { status: "completed" });
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  await expect(section.getByText(/9 of 10 completed/)).toBeVisible();
  await section.getByRole("button", { name: "Edit First student campaign" }).click();
  await section.getByRole("form", { name: "Edit First student campaign" }).getByLabel("Status").selectOption("completed");
  await section.getByRole("button", { name: "Save" }).click();
  await expect(status).toHaveText("Onboarding completed: the university is now Partner Activated.");
  await expect(section.getByText(/10 of 10 completed/)).toBeVisible();
  await expect(page.getByText("Partner Activated").first()).toBeVisible();
  await page.reload();
  await expect(section.locator("p .status").first()).toHaveText("Completed");

  // OB11: an overseas_admin reads it without Edit; the page fits a phone.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(universityPage);
  await expect(table.getByRole("row")).toHaveCount(11);
  await expect(section.getByRole("button", { name: /^Edit / })).toHaveCount(0);
  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  await expect(section.getByRole("heading", { name: "Partner onboarding" })).toBeVisible();
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
});
