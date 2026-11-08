import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { pickFromList } from "./helpers/pick";

// pob-011 (DEC-SCOPE-427): a requirement received via an (active, NDA, signed) vendor is created from the form with its vendor and a
// staff-only end client; candidates are shared with the vendor anonymised; a full-details share waits for consent; the shares list says
// "Vendor · Anonymised"; a later direct share of the same candidate to that end client warns (AC1). No sideways scroll on a phone.
const ADMIN = "superadmin@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const API = "/api/v1/recruiter";
const PDF = { name: "file.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n") };
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function apiSignIn(request: APIRequestContext, email: string) {
  await request.post("/api/v1/auth/logout");
  expect((await request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division: "it" } })).ok()).toBeTruthy();
}

async function ok(response: Awaited<ReturnType<APIRequestContext["post"]>>) {
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

/** An active vendor with an NDA and a signed agreement, a client company and two pool candidates -- all through the API. */
async function world(request: APIRequestContext, stamp: number) {
  await apiSignIn(request, RECRUITER);
  const vendor = (await ok(await request.post(`${API}/companies`, { data: { name: `POB11 Vendor ${stamp} Pvt`, partner_type: "vendor" } }))).company;
  const doc = (kind: string) => request.post(`${API}/companies/${vendor.id}/documents`, { multipart: { kind, file: PDF } });
  await ok(await doc("vendor_onboarding_form"));
  await ok(await doc("nda"));
  await ok(await request.post(`${API}/companies/${vendor.id}/vendor-status`, { data: { status: "registration_submitted", from_status: "prospect" } }));
  await ok(await request.post(`${API}/companies/${vendor.id}/contacts`, { data: { name: `Vendor Asha ${stamp}`, email: `vendor-${stamp}@example.com` } }));
  await ok(await request.post(`${API}/companies/${vendor.id}/contracts`, { data: { direction: "we_pay_vendor", confidentiality_terms: "Two years" } }));
  await ok(await request.put(`${API}/companies/${vendor.id}/contracts/document?kind=contract`, { multipart: { file: PDF } }));
  await ok(await request.patch(`${API}/companies/${vendor.id}/contracts`, { data: { status: "signed", from_status: "discussion" } }));
  const client = (await ok(await request.post(`${API}/companies`, { data: { name: `POB11 Client ${stamp} Ltd` } }))).company;
  const sources = await (await request.get(`${API}/catalogue/candidate-sources?limit=100`)).json();
  const source_id = sources.items.find((s: { active: boolean }) => s.active).id;
  const people = [];
  for (const n of [1, 2]) {
    people.push((await ok(await request.post(`${API}/candidates`, { data: { name: `POB11 Cand${n} ${stamp}`, email: `pob11-${n}-${stamp}@example.com`, source_id } }))));
  }
  await apiSignIn(request, ADMIN);
  await ok(await request.post(`${API}/companies/${vendor.id}/vendor-status`, { data: { status: "approved", from_status: "registration_submitted" } }));
  await apiSignIn(request, RECRUITER);
  await ok(await request.post(`${API}/companies/${vendor.id}/vendor-status`, { data: { status: "active", from_status: "approved" } }));
  return { vendor, client, people };
}

test("a vendor requirement is shared with the vendor anonymised, and a direct share to the same end client warns", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const { vendor, client, people } = await world(page.request, stamp);

  // The form: the company is the end client; the vendor and the disclosure are the Source section.
  await page.goto("/recruiter/requirements/new");
  await pickFromList(page.getByRole("combobox", { name: "Company (required)" }), client.name, client.name);
  await pickFromList(page.getByRole("combobox", { name: "Via vendor (optional)" }), vendor.name, vendor.name);
  await page.getByLabel("End client name").selectOption("internal");
  await page.getByLabel("Job title").fill(`POB11 Java ${stamp}`);
  await page.getByLabel("Job location").fill("Pune");
  await page.getByRole("button", { name: "Save requirement" }).click();
  await page.waitForURL(/\/recruiter\/requirements\/[0-9a-f-]{36}/);
  const requirementId = page.url().split("/").pop()!.split("?")[0];
  await expect(page.getByRole("link", { name: vendor.name })).toBeVisible();
  await expect(page.getByText("Staff only (candidates see “Confidential client”)")).toBeVisible();

  // Two candidates on the requirement, then share them with the vendor.
  for (const person of people) {
    await ok(await page.request.post(`${API}/requirements/${requirementId}/candidates`, { data: { candidate_id: person.id } }));
  }
  await page.reload();
  for (const person of people) await page.getByLabel(`Select ${person.name} to share`).check();
  await page.getByRole("button", { name: "Share selected (2)" }).click();
  const dialog = page.getByRole("form", { name: "Share 2 profiles" });
  await dialog.getByLabel(new RegExp(`Vendor: ${vendor.name}`)).check();
  await expect(dialog.getByLabel(/^Portal/)).toHaveCount(0);
  await dialog.getByLabel(/^Other/).check();
  await expect(dialog.getByLabel(/^Anonymised/)).toBeChecked();

  // Full details wait for the candidates' consent.
  await dialog.getByLabel(/^Full details/).check();
  await expect(dialog.getByRole("button", { name: "Share 2 profiles" })).toBeDisabled();
  await dialog.getByLabel(/^Anonymised/).check();
  await dialog.getByRole("button", { name: "Share 2 profiles" }).click();
  await expect(page.getByRole("status").filter({ hasText: "(vendor, anonymised)" })).toBeVisible();
  await page.getByRole("region", { name: "Profiles shared" }).getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Vendor · Anonymised").first()).toBeVisible();

  // AC1: the same candidate shared directly for another requirement of that end client warns about the duplicate.
  const direct = (await ok(await page.request.post(`${API}/requirements`, { data: { company_id: client.id, title: `POB11 Direct ${stamp}`, location: "Pune" } }))).requirement;
  const repeat = await page.request.post(`${API}/shares`, { data: { requirement_id: direct.id, candidate_ids: [people[0].id], channel: "other" } });
  expect(repeat.status()).toBe(409);
  expect((await repeat.json()).detail.message).toContain("with its end client through another route");

  // The detail fits a phone.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/recruiter/requirements/${requirementId}`);
  await expect(page.getByRole("link", { name: vendor.name })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
