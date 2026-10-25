import { test, expect, type Page } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-041 (DEC-SCOPE-278 G6) -- the Appendix B sample journey through the counselor's pages: a walk-in enquiry is qualified and
// converted; the student gets three applications -- A is missing a transcript, B has a conditional offer, C is rejected through the
// Record outcome form -- and the student 360 shows three independent statuses that C's rejection never touched; B is then accepted,
// gets its visa and is enrolled while A and C stay as they were. Steps without a page of their own (creating applications, recording the
// offer, visa and enrolment) use the same routes the pages call. Requires the stack with `python -m app.seed` applied.
test.describe.configure({ timeout: 240_000 });

const PDF = { name: "file.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
const mobile = () => `9${String(Date.now()).slice(-9)}`;
const APPS = "/api/v1/workflows/overseas/applications";

async function ok(response: Awaited<ReturnType<Page["request"]["get"]>>, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

async function applicationCard(page: Page, university: string) {
  return page.locator(".s360-list > li", { has: page.getByText(university, { exact: true }) });
}

test("the Appendix B journey: one student, three independent applications, B through to enrolment (ccrm-041)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await signInAsFreshCounselor(page, "ccrm041");

  // 1. The enquiry, qualified and converted on the lead page.
  const stamp = Date.now();
  const name = `Journey Student ${stamp}`;
  await page.goto("/overseas/counselor/leads/new");
  await page.getByLabel(/Student name/).fill(name);
  await page.getByLabel(/Mobile number/).fill(mobile());
  await page.getByLabel(/^Email/).fill(`ccrm041-${stamp}@example.local`);
  const product = page.getByLabel(/Product interest/);
  await expect(product.locator("option").nth(1)).toBeAttached();
  await product.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/overseas\/counselor\/leads\/[0-9a-f-]{36}$/);
  const leadUrl = new URL(page.url()).pathname;
  await page.getByRole("button", { name: "Set next action" }).click();
  await page.getByLabel("Action", { exact: true }).fill("Open the student account");
  await page.getByLabel("Due date").fill(day(2));
  await page.getByRole("button", { name: "Save next action" }).click();
  await expect(page.getByText("Next action saved.")).toBeVisible();
  await page.getByRole("button", { name: `Change stage for ${name}` }).click();
  await page.getByLabel(`New stage for ${name}`).selectOption("qualified");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Stage: Qualified", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Convert to student" }).click();
  await page.getByRole("form", { name: "Convert to student" }).getByRole("button", { name: "Create student account" }).click();
  await expect(page.getByText(`Student account created for ${name}`)).toBeVisible();
  await page.getByRole("link", { name: "Open the student's profile" }).click();
  await page.waitForURL(/\/overseas\/counselor\/students\/[0-9a-f-]{36}\/profile$/);
  const studentId = new URL(page.url()).pathname.split("/")[4];

  // 2. Three applications at three universities (C is worked on its page by university, below).
  // Names that appear once, so each application's card is found by its university (backend tests add same-named universities).
  const listed = (await ok(await page.request.get("/api/v1/public/universities"))) as { id: string; name: string }[];
  const universities = listed.filter((u) => listed.filter((v) => v.name === u.name).length === 1).slice(0, 3);
  expect(universities).toHaveLength(3);
  const [a, b] = await Promise.all(
    universities.map(async (u) => (await ok(await page.request.post(APPS, { data: { student_id: studentId, university_id: u.id, intake: "Fall 2027" } }), 201)).id as string),
  );

  // 3. A: the transcript is a required checklist item still missing, so Ready for submission is held back (ccrm-019).
  await ok(await page.request.post(`${APPS}/${a}/sub-status`, { data: { sub_status: "documents_pending" } }));
  await ok(await page.request.post(`${APPS}/${a}/checklist`), 201);
  await ok(await page.request.post(`${APPS}/${a}/checklist/items`, { data: { document_type: "Transcripts", required: true } }), 201);
  const held = await page.request.post(`${APPS}/${a}/sub-status`, { data: { sub_status: "ready_for_submission" } });
  expect(held.status()).toBe(409);
  expect(JSON.stringify(await held.json())).toContain("Transcripts");

  // 4. B: a conditional offer (ccrm-023).
  const letter = (await ok(await page.request.post(`${APPS}/${b}/offer-letters`, { multipart: { file: PDF } }), 201)).document;
  const offer = (await ok(await page.request.post(`${APPS}/${b}/offers`, { data: { offer_type: "conditional", issue_date: day(-1), offer_deadline: day(20), conditions: "IELTS 6.5", offer_document_id: letter.id } }), 201)).offer;

  // 5. C is rejected through the Record outcome form on the applications page (ccrm-015).
  await page.goto("/overseas/counselor/applications");
  const cCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: name }).filter({ hasText: universities[2].name }).first();
  await cCard.getByRole("button", { name: "Record outcome" }).click();
  const form = cCard.getByRole("form", { name: "Record outcome" });
  await form.getByLabel("Outcome", { exact: true }).selectOption("rejected");
  await form.getByLabel("Reason", { exact: true }).fill("Grades below the cut-off");
  await form.getByRole("button", { name: "Record outcome" }).click();
  await expect(cCard.getByText(/Outcome recorded: Rejected/)).toBeVisible();

  // The 360 shows three independent statuses: A and B are exactly as they were before C was rejected (AC 3, AC 9).
  const tabUrl = `/overseas/counselor/students/${studentId}?tab=applications`;
  await page.goto(tabUrl);
  await expect((await applicationCard(page, universities[0].name)).getByText("Documents pending", { exact: true })).toBeVisible();
  await expect((await applicationCard(page, universities[1].name)).getByText("Conditional offer", { exact: true })).toBeVisible();
  await expect((await applicationCard(page, universities[2].name)).getByText(/Rejected/).first()).toBeVisible();
  for (const card of [await applicationCard(page, universities[0].name), await applicationCard(page, universities[1].name)]) {
    await expect(card.getByText(/Rejected/)).toHaveCount(0);
  }

  // 6. B: accepted, visa approved, enrolled (ccrm-025/026/027).
  await ok(await page.request.post(`${APPS}/${b}/offers/${offer.id}/decision`, { data: { decision: "accepted", decision_date: day(0) } }));
  const visa = await ok(await page.request.post("/api/v1/workflows/overseas/visa", { data: { application_id: b } }), 201);
  const steps: [string, string, Record<string, string>][] = [
    ["not_started", "preparing", {}],
    ["preparing", "appointment_booked", { appointment_date: day(1), appointment_place: "VFS Chennai" }],
    ["appointment_booked", "submitted", { submission_date: day(0) }],
    ["submitted", "approved", {}],
  ];
  for (const [current, target, extra] of steps) {
    await ok(await page.request.patch(`/api/v1/workflows/overseas/visa/${visa.id}/lifecycle`, { data: { expected_visa_status: current, visa_status: target, ...extra } }));
  }
  const confirmation = (await ok(await page.request.post(`${APPS}/${b}/enrollment-documents`, { multipart: { file: PDF } }), 201)).document;
  await ok(await page.request.put(`${APPS}/${b}/enrollment`, { data: { expected_status: "status_tracking", enrollment_date: day(0), enrollment_document_id: confirmation.id, pre_enrollment_checklist_complete: true } }));

  await page.goto(tabUrl);
  await expect((await applicationCard(page, universities[1].name)).getByText("Enrolled").first()).toBeVisible();
  await expect((await applicationCard(page, universities[0].name)).getByText("Documents pending", { exact: true })).toBeVisible();
  await expect((await applicationCard(page, universities[2].name)).getByText(/Rejected/).first()).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // The lead reads as Converted once its student is enrolled (tel-018).
  await page.goto(leadUrl);
  await expect(page.getByText("Stage: Converted", { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
