import { expect, test, type Page } from "@playwright/test";

// pob-018 (DEC-SCOPE-428): the seeded recruiter adds a candidate (AC1: a source and today's source date), cannot share them with a client
// before recording the permission to be represented (AC3), verifies the details (AC2), records the permission and then shares. The card
// stays on the page after a reload, and a phone shows it without sideways scroll.
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

test("a recruiter records where a candidate came from, verifies them and records their permission before sharing", async ({ page }) => {
  test.setTimeout(120_000);
  const tag = Date.now().toString(36);
  await signIn(page, RECRUITER);
  const sources = (await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json()).items as { id: string; name: string }[];
  const vendorSource = sources.find((s) => s.name === "Vendor");
  expect(vendorSource, "A1: the Vendor source is seeded").toBeTruthy();
  const made = await page.request.post("/api/v1/recruiter/candidates", {
    data: { name: `POB18 Asha ${tag}`, email: `pob18-${tag}@example.com`, source_id: vendorSource!.id, source_detail: "Vendor shortlist", lawful_basis: "provided_for_placement" },
  });
  expect(made.status(), await made.text()).toBe(201);
  const candidate = await made.json();
  expect(candidate.sourcing.source_date).toBe(istToday()); // AC1

  // a requirement to share with; AC3: no permission yet, so the share is refused and names the candidate
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `POB18 Co ${tag} Ltd` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const requirement = (await (await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `POB18 Dev ${tag}`, location: "Pune" } })).json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }
  const share = () => page.request.post("/api/v1/recruiter/shares", { data: { requirement_id: requirement.id, candidate_ids: [candidate.id], channel: "other" } });
  const refused = await share();
  expect(refused.status()).toBe(422);
  expect(await refused.text()).toContain(candidate.candidate_code);

  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const card = page.getByRole("region", { name: "Source and outreach" });
  await expect(card.getByText("Vendor shortlist")).toBeVisible();
  await expect(card.getByText("Not verified yet")).toBeVisible();
  await expect(card.getByText(/No permission recorded/)).toBeVisible();

  // AC2: Verify details
  await card.getByRole("button", { name: "Verify details" }).click();
  await expect(card.getByText("Details verified.")).toBeVisible();
  await expect(card.getByText("Not verified yet")).toHaveCount(0);

  // A5: the permission, refused without the method, then recorded
  await card.getByRole("button", { name: "Update outreach" }).click();
  await card.getByLabel("Outreach status").selectOption("consented");
  await card.getByLabel("How they agreed").selectOption("call");
  await card.getByLabel("Note (optional)").fill("Agreed on the phone");
  await card.getByRole("button", { name: "Save outreach" }).click();
  await expect(card.getByText("Outreach updated.")).toBeVisible();
  await expect(card.getByText(/Agreed on the phone/)).toBeVisible();

  await page.reload();
  await expect(page.getByRole("region", { name: "Source and outreach" }).getByText(/Phone call on/)).toBeVisible();
  expect((await share()).status()).toBe(201); // AC3: with the permission the share goes through

  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBe(true);
});
