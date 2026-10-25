import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

// ccrm-022 (DEC-SCOPE-263, AC 10) -- identity / financial documents are marked for the counselor, hidden from the university rep and
// never opened by them; /files/download no longer hands out a document's file. Requires the stack with `python -m app.seed` applied;
// creates its own application and documents at the seeded rep's university (University of Manchester), never touching seeded ones.

const login = (request: APIRequestContext, email: string) => request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division: "overseas" } });

async function documentsAtTheRepsUniversity(page: Page, stamp: number) {
  await login(page.request, "counselor@edusphere.local");
  const counselorId = (await (await page.request.get("/api/v1/auth/me")).json()).id as string;
  await login(page.request, "student.overseas@edusphere.local");
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; slug: string }[];
  const manchester = universities.find((u) => u.slug === "university-of-manchester") ?? universities[0];
  const created = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: manchester.id, counselor_id: counselorId } });
  // A re-run finds the student's application there already (one per university/course): reuse it, assigned to the seeded counselor.
  let applicationId = created.ok() ? ((await created.json()).id as string) : null;
  if (!applicationId) {
    const name = (await (await page.request.get(`/api/v1/public/universities/${manchester.slug}`)).json()).university.name as string;
    const rows = (await (await page.request.get("/api/v1/portal/overseas/student/applications")).json()).rows as { id: string; university: string }[];
    applicationId = rows.find((r) => r.university === name)!.id;
    await login(page.request, "overseasadmin@edusphere.local");
    await page.request.put(`/api/v1/workflows/overseas/applications/${applicationId}/counselor`, { data: { counselor_id: counselorId } });
    await login(page.request, "student.overseas@edusphere.local");
  }
  const application = { id: applicationId };
  const ids: Record<string, string> = {};
  for (const [name, type] of [["passport", `Passport E2E ${stamp}`], ["bank", `Bank statement E2E ${stamp}`], ["transcript", `Transcript E2E ${stamp}`]]) {
    const created = await page.request.post("/api/v1/workflows/overseas/documents", { data: { application_id: application.id, document_type: type, file_url: `uploads/e2e-${name}-${stamp}.pdf` } });
    ids[name] = (await created.json()).id;
  }
  return ids;
}

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("the counselor sees which documents are sensitive and can still open them", async ({ page }) => {
  const stamp = Date.now();
  await documentsAtTheRepsUniversity(page, stamp);
  await signIn(page, "counselor@edusphere.local", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/documents");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Document Verification" }) }).last();
  await expect(panel.locator(".card", { hasText: `Passport E2E ${stamp}` })).toContainText("Sensitive · Identity");
  await expect(panel.locator(".card", { hasText: `Bank statement E2E ${stamp}` })).toContainText("Sensitive · Financial");
  await expect(panel.locator(".card", { hasText: `Transcript E2E ${stamp}` })).not.toContainText("Sensitive");
  await expect(panel.locator(".card", { hasText: `Passport E2E ${stamp}` }).locator(".badge")).toHaveText("Pending review"); // the status badge is unchanged
});

test("a university rep never sees or opens an identity or financial document, and /files/download refuses document keys", async ({ page }) => {
  const stamp = Date.now();
  const ids = await documentsAtTheRepsUniversity(page, stamp);
  await login(page.request, "university.rep@edusphere.local");
  const rows = ((await (await page.request.get("/api/v1/portal/overseas/university/documents")).json()).rows ?? []) as { document: string }[];
  const mine = rows.map((r) => r.document).filter((d) => d.endsWith(`E2E ${stamp}`));
  expect(mine).toEqual([`Transcript E2E ${stamp}`]);
  expect((await page.request.get(`/api/v1/workflows/overseas/documents/${ids.bank}/download`)).status()).toBe(403);
  expect((await page.request.get(`/api/v1/workflows/overseas/documents/${ids.passport}/download`)).status()).toBe(403);
  const keyed = await page.request.get(`/api/v1/files/download?key=${encodeURIComponent(`uploads/e2e-bank-${stamp}.pdf`)}`);
  expect(keyed.status()).toBe(404);
});

test("the Overseas Admin chooses an item's sensitivity on a checklist template", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/checklists");
  await page.getByRole("button", { name: /New template/ }).click();
  const first = page.getByRole("listitem", { name: "Document 1" });
  await expect(first.getByLabel("Sensitivity")).toHaveValue("identity"); // Passport
  await first.getByLabel("Document type").selectOption("Transcripts");
  await expect(first.getByLabel("Sensitivity")).toHaveValue("standard");
  await first.getByLabel("Sensitivity").selectOption("financial");
  await expect(first.getByLabel("Sensitivity")).toHaveValue("financial");
});
