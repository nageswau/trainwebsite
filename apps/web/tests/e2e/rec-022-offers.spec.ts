import { expect, test, type Page } from "@playwright/test";

// rec-022 (AC1, AC2; OF3-OF8): the seeded recruiter records an offer for a Selected candidate (a Shortlisted one has no "+ Record offer"),
// uploads the letter, moves it Offer Pending -> Offer Received -> Accepted, and the history shows each step; the seeded placement manager
// reads it without any write control. Declined -> Withdrawn, the legacy routes (AC3) and the student's own view are covered by
// test_rec_022_offers.py and the component tests.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

test("offers: record for a Selected candidate, upload the letter, Received then Accepted with history; the manager reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const name = `E2E Offeree ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/recruiter/") && response.status() >= 500 && failedCalls.push(response.url()));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec022 ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `Java Developer ${stamp}`, location: "Pune" } });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;

  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(`8${String(stamp).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateId = page.url().split("/").at(-1)?.split("?")[0];
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId, status: "shortlisted" } });
  expect(added.status()).toBe(201);
  const applicationId = (await added.json()).application.id as string;

  // AC1: a Shortlisted candidate has no offer button.
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Offer of ${name}` }).click();
  await expect(candidates.getByText("No offer yet.")).toBeVisible();
  await expect(candidates.getByRole("button", { name: `+ Record offer for ${name}` })).toHaveCount(0);

  // Selected -> "+ Record offer", the position starting from the requirement title.
  expect((await page.request.post(`/api/v1/recruiter/applications/${applicationId}/status`, { data: { status: "selected" } })).ok()).toBeTruthy();
  await page.reload();
  await candidates.getByRole("button", { name: `Offer of ${name}` }).click();
  await candidates.getByRole("button", { name: `+ Record offer for ${name}` }).click();
  const form = candidates.getByRole("form", { name: "Record offer" });
  await expect(form.getByLabel("Position (required)")).toHaveValue(`Java Developer ${stamp}`);
  await form.getByLabel("Salary (per year)").fill("600000");
  await form.getByRole("button", { name: "Save offer" }).click();
  await expect(candidates.getByRole("status").first()).toContainText(`Offer recorded for ${name}.`);
  const offer = candidates.getByRole("region", { name: `Offer for ${name}` });
  await expect(offer.locator(".badge")).toHaveText("Offer Pending");
  await expect(offer).toContainText("INR 6,00,000.00");

  // OF7: the letter.
  await offer.getByLabel("Upload offer letter").setInputFiles({ name: "offer-letter.pdf", mimeType: "application/pdf", buffer: PDF });
  await offer.getByRole("button", { name: "Upload" }).click();
  await expect(candidates.getByRole("status").first()).toContainText(`Offer letter uploaded for ${name}.`);
  await expect(offer.getByRole("link", { name: /Download offer letter/ })).toBeVisible();
  const letter = await page.request.get(`/api/v1/recruiter/offers/${(await (await page.request.get(`/api/v1/recruiter/applications/${applicationId}/offer`)).json()).offer.id}/letter`);
  expect(letter.ok()).toBeTruthy();
  expect(letter.headers()["content-type"]).toBe("application/pdf");

  // OF3 / AC2: Offer Received, then Accepted; the history keeps each step.
  for (const target of ["Offer Received", "Accepted"]) {
    await offer.getByRole("button", { name: /Change status/ }).click();
    await offer.getByLabel("New status (required)").selectOption({ label: target });
    await offer.getByRole("button", { name: "Save status" }).click();
    await expect(offer.locator(".badge")).toHaveText(target);
  }
  await expect(offer.getByRole("button", { name: /Change status|Edit offer/ })).toHaveCount(0);
  await offer.getByText(/History \(\d+\)/).click();
  for (const text of ["Recorded as Offer Pending", "Offer letter uploaded", "Offer Pending → Offer Received", "Offer Received → Accepted"]) {
    await expect(offer).toContainText(text);
  }
  const row = candidates.getByRole("list", { name: "Candidates on this requirement" }).getByRole("listitem").first();
  await expect(row.locator(".badge").first()).toHaveText("Selected"); // OF6: accepted is not yet joined (rec-023)

  // OF8: the manager reads the offer with no write control.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(`/recruiter/requirements/${requirementId}`);
  await candidates.getByRole("button", { name: `Offer of ${name}` }).click();
  await expect(offer.locator(".badge")).toHaveText("Accepted");
  await expect(offer.getByLabel(/Upload offer letter|Replace offer letter/)).toHaveCount(0);

  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
