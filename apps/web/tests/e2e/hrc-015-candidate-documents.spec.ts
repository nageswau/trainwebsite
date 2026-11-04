import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

// hrc-015 (DEC-SCOPE-379): AC1 a DOC resume uploads and previews (the worker's LibreOffice rendition, so the stack's `worker` must run);
// AC3 links are short-lived signed URLs; AC2 a requested document shows pending, then received once the student uploads it from the
// student portal. Seeded demo accounts (`python -m app.seed`); candidates are created per run.
const DOC = readFileSync(path.join(__dirname, "fixtures", "hrc-015-resume.doc"));
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const STUDENT = { email: "student.it@edusphere.local", password: "Demo@123", division: "it" };

async function signIn(page: Page, email: string, division = "it") {
  expect((await page.request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division } })).ok()).toBeTruthy();
}

async function newCandidate(page: Page): Promise<string> {
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const stamp = `${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
  const created = await page.request.post("/api/v1/recruiter/candidates", {
    data: { name: `HRC Docs ${stamp}`, email: `hrc015-${stamp}@example.com`, source_id: sources.items.find((s: { active: boolean }) => s.active).id },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

test("a DOC resume uploads and previews through its PDF rendition; links are signed and short-lived (AC1, AC3)", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "placement@edusphere.local");
  const id = await newCandidate(page);
  await page.goto(`/recruiter/candidates/${id}`);
  await page.getByLabel("Upload resume").setInputFiles({ name: "asha.doc", mimeType: "application/msword", buffer: DOC });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("Resume version 1 uploaded.")).toBeVisible();

  const resume = page.locator("section", { has: page.getByRole("heading", { name: "Resume", exact: true }) });
  await resume.getByRole("button", { name: "Preview resume version 1" }).click();
  const frame = resume.getByTitle("Preview of resume version 1");
  await expect(async () => {
    if (!(await frame.isVisible())) await resume.getByRole("button", { name: "Check again" }).click({ timeout: 2_000 });
    await expect(frame).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 90_000, intervals: [3_000] });
  const src = await frame.getAttribute("src");
  expect(src).toMatch(/^\/api\/v1\/files\/signed\//);
  const rendition = await page.request.get(src!);
  expect(rendition.headers()["content-type"]).toBe("application/pdf");
  expect((await rendition.body()).subarray(0, 5).toString()).toBe("%PDF-");

  const link = await (await page.request.get(`/api/v1/recruiter/candidates/${id}/resume/1/link?mode=download`)).json();
  expect(link.expires_in).toBe(300);
  const original = await page.request.get(link.url);
  expect(original.headers()["content-disposition"]).toMatch(/^attachment; filename="resume-CAN-\d+-v1\.doc"$/);
  expect((await page.request.get(`${link.url.slice(0, -4)}AAAA`)).status()).toBe(404); // a tampered token is refused
});

test("a requested document shows pending, then received after the student uploads it (AC2)", async ({ page }) => {
  test.setTimeout(60_000);
  const note = `Your Python course certificate ${Date.now()}`;
  expect((await page.request.post("/api/v1/auth/login", { data: STUDENT })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/account/placement-pool/opt-in", { data: { consent_version: "v1" } })).ok()).toBeTruthy();
  const studentName = (await (await page.request.get("/api/v1/auth/me")).json()).full_name as string;

  await signIn(page, "placement@edusphere.local");
  const found = await (await page.request.get("/api/v1/recruiter/candidates", { params: { q: studentName, limit: 5 } })).json();
  const candidateId = found.items[0].id as string;
  for (const r of (await (await page.request.get(`/api/v1/recruiter/candidates/${candidateId}/documents`)).json()).requests) {
    if (r.status === "pending") await page.request.post(`/api/v1/recruiter/candidates/${candidateId}/document-requests/${r.id}/cancel`);
  }
  await page.goto(`/recruiter/candidates/${candidateId}`);
  const docs = page.locator("section", { has: page.getByRole("heading", { name: "Documents", exact: true }) });
  await docs.getByLabel("Document to request").selectOption("certificate");
  await docs.getByLabel("Note for the candidate (optional)").fill(note);
  await docs.getByRole("button", { name: "Request document" }).click();
  await expect(docs.getByText("Document requested.")).toBeVisible();
  const requested = docs.getByRole("list", { name: "Requested documents" }).locator("li", { hasText: note });
  await expect(requested.getByText("Pending", { exact: true })).toBeVisible();

  expect((await page.request.post("/api/v1/auth/login", { data: STUDENT })).ok()).toBeTruthy();
  await page.goto("/it/student/placement-status");
  const mine = page.locator("section", { has: page.getByRole("heading", { name: "Documents for placement" }) });
  const ask = mine.getByRole("list", { name: "Documents the placement team asked for" }).locator("li", { hasText: note });
  await expect(ask.getByText("Pending", { exact: true })).toBeVisible();
  const request = (await (await page.request.get("/api/v1/account/candidate-documents")).json()).requests.find((r: { note: string; status: string }) => r.note === note && r.status === "pending");
  await mine.getByLabel("Fulfils request (optional)").selectOption(request.id);
  await mine.getByLabel("File").setInputFiles({ name: "python-certificate.pdf", mimeType: "application/pdf", buffer: PDF });
  await mine.getByRole("button", { name: "Upload document" }).click();
  await expect(mine.getByText("Document uploaded.")).toBeVisible();
  await expect(ask.getByText("Received", { exact: true })).toBeVisible();
  await expect(mine.getByRole("list", { name: "Your documents" }).getByText("python-certificate.pdf", { exact: false }).first()).toBeVisible();

  await signIn(page, "placement@edusphere.local");
  await page.goto(`/recruiter/candidates/${candidateId}`);
  await expect(requested.getByText("Received", { exact: true })).toBeVisible();
});
