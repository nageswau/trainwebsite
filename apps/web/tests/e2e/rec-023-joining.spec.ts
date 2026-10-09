import { expect, test, type Page } from "@playwright/test";

// rec-023 (AC1, AC2; JN2-JN8): the seeded recruiter's Accepted offer shows a Pending joining and appears in "Joining due"; Joined without
// the actual date is refused on its field; Joined with the date and confirmation moves the candidate to Joined and closes the one-vacancy
// requirement; a second candidate is marked Did Not Join with a reason (-> Withdrawn). The manager reads the Joinings page; the page holds
// at phone width. Proof upload, the IDOR and role rules are covered by test_rec_023_joining.py and the component tests.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const istToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

/** A candidate through the UI form (the API's create needs the same fields), then on the requirement, Selected, offered and Accepted. */
async function acceptedOffer(page: Page, requirementId: string, name: string, mobile: string): Promise<string> {
  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(mobile);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateId = page.url().split("/").at(-1)?.split("?")[0];
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId, status: "shortlisted" } });
  expect(added.status()).toBe(201);
  const applicationId = (await added.json()).application.id as string;
  expect((await page.request.post(`/api/v1/recruiter/applications/${applicationId}/status`, { data: { status: "selected" } })).ok()).toBeTruthy();
  const offer = await page.request.post(`/api/v1/recruiter/applications/${applicationId}/offer`, { data: { position: "Java Developer" } });
  expect(offer.status()).toBe(201);
  const offerId = (await offer.json()).offer.id as string;
  expect((await page.request.post(`/api/v1/recruiter/offers/${offerId}/status`, { data: { status: "accepted" } })).ok()).toBeTruthy();
  return offerId;
}

test("joining: due list, Joined closes the one-vacancy requirement, Did Not Join withdraws; the manager reads; mobile", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const joiner = `E2E Joiner ${stamp}`;
  const stayer = `E2E Stayer ${stamp}`;
  const consoleErrors: string[] = [];
  // The one 422 this test provokes on purpose (Joined without the actual date) is logged by the browser; any other error fails the test.
  const expected422 = /status of 422/;
  page.on("console", (message) => message.type() === "error" && !expected422.test(message.text()) && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/recruiter/") && response.status() >= 500 && failedCalls.push(response.url()));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec023 ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", {
    data: { company_id: (await company.json()).company.id, title: `Java Developer ${stamp}`, location: "Pune", vacancies: 1 },
  });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;
  await acceptedOffer(page, requirementId, joiner, `7${String(stamp).slice(-9)}`);
  await acceptedOffer(page, requirementId, stayer, `6${String(stamp).slice(-9)}`);

  // "Joining due" lists both, with a link to the requirement.
  await page.goto("/recruiter/joinings");
  const due = page.getByRole("list", { name: "Joinings" });
  await expect(due).toContainText(joiner);
  await expect(due).toContainText(stayer);
  await expect(page.getByRole("button", { name: /^Joining due \(\d+\)$/ })).toHaveAttribute("aria-current", "page");

  // AC1: Joined needs the actual date (the API's 422 on its field), then the date and who confirmed it.
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  await candidates.getByRole("button", { name: `Offer of ${joiner}` }).click();
  const joining = candidates.getByRole("region", { name: `Joining for ${joiner}` });
  await expect(joining.locator(".badge").first()).toHaveText("Pending");
  await joining.getByRole("button", { name: /Update joining/ }).click();
  const form = joining.getByRole("form", { name: "Update joining" });
  await form.getByLabel("Joining status").selectOption({ label: "Joined" });
  await form.getByLabel("Joining location").fill("Pune office");
  await form.getByRole("button", { name: "Save joining" }).click();
  await expect(form).toContainText("Enter the actual joining date to mark Joined");
  await form.getByLabel(/Actual joining date/).fill(istToday());
  await form.getByLabel(/Confirmed by/).fill("HR - Priya");
  await form.getByRole("button", { name: "Save joining" }).click();
  await expect(candidates.getByRole("status").first()).toContainText(`Joining for ${joiner} is now Joined.`);
  await expect(joining.locator(".badge").first()).toHaveText("Joined");
  await expect(joining).toContainText("Pune office");
  await expect(joining.getByRole("button", { name: /Update joining/ })).toHaveCount(0);

  // JN7: the application is Joined and the one-vacancy requirement is Closed.
  const requirement = await (await page.request.get(`/api/v1/recruiter/requirements/${requirementId}`)).json();
  expect(requirement.requirement?.status ?? requirement.status).toBe("closed");

  // AC2: Did Not Join needs a reason; it withdraws the candidate.
  await page.reload();
  await candidates.getByRole("button", { name: `Offer of ${stayer}` }).click();
  const second = candidates.getByRole("region", { name: `Joining for ${stayer}` });
  await second.getByRole("button", { name: /Update joining/ }).click();
  const form2 = second.getByRole("form", { name: "Update joining" });
  await form2.getByLabel("Joining status").selectOption({ label: "Did Not Join" });
  await form2.getByLabel(/Reason/).fill("Took another offer");
  await form2.getByRole("button", { name: "Save joining" }).click();
  await expect(second.locator(".badge").first()).toHaveText("Did Not Join");
  await expect(second).toContainText("Took another offer");

  // The lists: Joined and Did not join.
  await page.goto("/recruiter/joinings?view=joined");
  await expect(page.getByRole("list", { name: "Joinings" })).toContainText(joiner);
  await page.getByRole("button", { name: /^Did not join/ }).click();
  await expect(page.getByRole("list", { name: "Joinings" })).toContainText("Reason: Took another offer");

  // The manager reads the Joinings page; the page holds at phone width.
  await page.context().clearCookies();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/recruiter/joinings?view=joined");
  await expect(page.getByRole("list", { name: "Joinings" })).toContainText(joiner);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
