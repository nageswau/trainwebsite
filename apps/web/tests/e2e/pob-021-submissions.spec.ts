import { expect, test, type Page } from "@playwright/test";

// pob-021 (DEC-SCOPE-430): the seeded recruiter submits a candidate from the requirement page. The wizard needs consent and confirmed
// interest (AC1), the submission gets a SUB- code with its skills match (AC3) and the client follow-up at the SLA (AC4); a duplicate to the
// same client on another requirement warns (AC2); a status change with its rejection reason is saved and shown (AC5). A phone shows it
// without sideways scroll.
const RECRUITER = "placement@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const istToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("a recruiter submits a consented candidate, sees the code, match and follow-up, and records a rejection", async ({ page }) => {
  test.setTimeout(150_000);
  const tag = Date.now().toString(36);
  await signIn(page, RECRUITER);
  const sources = (await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json()).items as { id: string; name: string }[];
  const made = await page.request.post("/api/v1/recruiter/candidates", {
    data: { name: `POB21 Asha ${tag}`, email: `pob21-${tag}@example.com`, location: "Pune", source_id: sources[0].id, lawful_basis: "provided_for_placement" },
  });
  expect(made.status(), await made.text()).toBe(201);
  const candidate = await made.json();
  const outreach = await page.request.put(`/api/v1/recruiter/candidates/${candidate.id}/outreach`, { data: { status: "consented", method: "call", given_on: istToday() } });
  expect(outreach.ok(), await outreach.text()).toBeTruthy();

  const company = (await (await page.request.post("/api/v1/recruiter/companies", { data: { name: `POB21 Co ${tag} Ltd`, submission_sla_hours: 24 } })).json()).company;
  expect(company.submission_sla_hours).toBe(24);
  const requirement = async (title: string) => {
    const r = (await (await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: company.id, title, location: "Pune" } })).json()).requirement;
    if (r.status === "new") expect((await page.request.post(`/api/v1/recruiter/requirements/${r.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
    return r;
  };
  const first = await requirement(`POB21 Dev ${tag}`);
  expect((await page.request.post(`/api/v1/recruiter/requirements/${first.id}/candidates`, { data: { candidate_id: candidate.id } })).ok()).toBeTruthy();

  await page.goto(`/recruiter/requirements/${first.id}`);
  await page.getByRole("checkbox", { name: `Select ${candidate.name} to share` }).check();
  await page.getByRole("button", { name: /Share selected/ }).click();
  const wizard = page.getByRole("form", { name: "Share 1 profile" });
  await wizard.getByLabel(/^Other/).check();
  const submit = wizard.getByRole("button", { name: "Share 1 profile" });
  await expect(submit).toBeDisabled(); // AC1: consent and interest first
  await wizard.getByLabel(/candidates agreed/).check();
  await wizard.getByLabel(/How and when they agreed/).fill("Phone call today");
  await wizard.getByLabel(/confirmed their interest/).check();
  await submit.click();
  await expect(page.getByText(/Shared 1 profile for/)).toBeVisible();

  await page.reload();
  const shared = page.getByRole("list", { name: "Shares" });
  await expect(shared.getByText(/^SUB-\d{6}$/)).toBeVisible(); // B1
  await expect(shared.getByText("Submitted")).toBeVisible();
  await expect(shared.getByText(/Client follow-up due/)).toBeVisible(); // AC4
  await expect(shared.getByText(/^Skills match:/)).toHaveCount(0); // no scored skills on this requirement: no empty line

  // AC5: rejected with a reason
  await shared.getByRole("button", { name: `Update submission for ${candidate.name}` }).click();
  const form = page.getByRole("form", { name: `Update submission for ${candidate.name}` });
  await form.getByLabel("Submission status").selectOption("rejected");
  await expect(form.getByRole("button", { name: "Save" })).toBeDisabled();
  await form.getByLabel(/Rejection reason/).selectOption("position_filled");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`Submission updated for ${candidate.name}.`)).toBeVisible();
  await expect(shared.getByText("Rejection reason: Position filled")).toBeVisible();

  // AC2: the same client on another requirement warns
  const second = await requirement(`POB21 QA ${tag}`);
  const again = await page.request.post("/api/v1/recruiter/shares", {
    data: { requirement_id: second.id, candidate_ids: [candidate.id], channel: "other", consent_confirmed: true, consent_reference: "Call", interest_confirmed: true },
  });
  expect(again.status()).toBe(409);
  expect((await again.json()).detail.duplicates[0].id).toBe(candidate.id);

  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBe(true);
});
