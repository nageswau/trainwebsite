import { expect, test, type Page } from "@playwright/test";

// pob-030 (DEC-SCOPE-440 G1-G7): the share gate. A self-registered employer's company is assigned to the seeded recruiter, who adds two
// candidates to a requirement -- Rahul with a recorded permission to be represented and a resume, Priya without. Sharing both is refused
// inline naming Priya; Rahul alone shares on the Portal and the employer can download his resume. After Rahul's permission is withdrawn
// the employer card offers no download ("Resume on request") and the resume URL is 404, while the share stays listed. Phone width too.

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), `${url} → ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test("share gate: an unpermitted candidate is refused inline; a withdrawn permission stops the employer's resume download", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const recruiterId = (await (await page.request.get("/api/v1/auth/me")).json()).id;
  await page.request.post("/api/v1/auth/logout");
  const employerEmail = `pob030-${stamp}@example.local`;
  const registered = await post(page, "/api/v1/employer/register", {
    email: employerEmail, password: "Sup3r-Secret-Pass!", full_name: "Gate Employer", company_name: `E2E Gate ${stamp}`, company_website: "https://example.com",
  });
  const companyId = registered.company.id;
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await post(page, `/api/v1/recruiter/companies/${companyId}/assign`, { recruiter_user_id: recruiterId });
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await post(page, `/api/v1/recruiter/companies/${companyId}/contacts`, { name: "Meera Iyer", mobile: "98450 12345", email: `hr${stamp}@example.com` });
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const rahul = await post(page, "/api/v1/recruiter/candidates", { name: `Rahul ${stamp}`, email: `rahul${stamp}@example.com`, source_id: source, location: "Pune" });
  const priya = await post(page, "/api/v1/recruiter/candidates", { name: `Priya ${stamp}`, email: `priya${stamp}@example.com`, source_id: source, location: "Pune" });
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const outreach = (status: string) => page.request.put(`/api/v1/recruiter/candidates/${rahul.id}/outreach`, { data: status === "consented" ? { status, method: "call", given_on: today } : { status } });
  expect((await outreach("consented")).ok()).toBeTruthy();
  expect((await page.request.put(`/api/v1/recruiter/candidates/${rahul.id}/resume`, { multipart: { file: { name: "cv.pdf", mimeType: "application/pdf", buffer: PDF } } })).ok()).toBeTruthy();
  const requirement = (await post(page, "/api/v1/recruiter/requirements", { company_id: companyId, title: `Gate Developer ${stamp}`, location: "Pune" })).requirement;
  await post(page, `/api/v1/recruiter/requirements/${requirement.id}/status`, { status: "requirement_received" });
  for (const c of [rahul, priya]) await post(page, `/api/v1/recruiter/requirements/${requirement.id}/candidates`, { candidate_id: c.id, status: "shortlisted" });

  // AC2: Priya has no permission to be represented -- the gate refuses the share inline and names her.
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const board = page.getByRole("region", { name: /^Candidates/ });
  await board.getByRole("checkbox", { name: `Select Rahul ${stamp} to share` }).check();
  await board.getByRole("checkbox", { name: `Select Priya ${stamp} to share` }).check();
  await board.getByRole("button", { name: "Share selected (2)" }).click();
  const dialog = board.getByRole("form", { name: "Share 2 profiles" });
  await dialog.getByLabel(/^Portal/).check();
  await dialog.getByLabel(/candidates agreed/).check();
  await dialog.getByLabel(/How and when they agreed/).fill("Phone call today");
  await dialog.getByLabel(/confirmed their interest/).check();
  await dialog.getByRole("button", { name: "Share 2 profiles" }).click();
  const refusal = dialog.locator("p[role=alert]");
  await expect(refusal).toContainText("permission to be represented");
  await expect(refusal).toContainText(`Priya ${stamp} (${priya.candidate_code})`);
  await expect(refusal).not.toContainText(`Rahul ${stamp}`);

  // Rahul alone shares.
  await page.reload();
  await board.getByRole("checkbox", { name: `Select Rahul ${stamp} to share` }).check();
  await board.getByRole("button", { name: "Share selected (1)" }).click();
  const single = board.getByRole("form", { name: "Share 1 profile" });
  await single.getByLabel(/^Portal/).check();
  await single.getByLabel(/candidates agreed/).check();
  await single.getByLabel(/How and when they agreed/).fill("Phone call today");
  await single.getByLabel(/confirmed their interest/).check();
  await single.getByRole("button", { name: "Share 1 profile" }).click();
  await expect(board.getByText(`Shared 1 profile for Gate Developer ${stamp} by Portal with Meera Iyer.`)).toBeVisible();

  // The employer downloads the resume while the permission stands.
  await page.request.post("/api/v1/auth/logout");
  await page.request.post("/api/v1/auth/login", { data: { email: employerEmail, password: "Sup3r-Secret-Pass!", division: "it" } });
  await page.goto("/it/employer/dashboard");
  const portal = page.getByRole("region", { name: /^Shared with you/ });
  const card = portal.getByRole("listitem").filter({ hasText: `Rahul ${stamp}` });
  const download = card.getByRole("link", { name: /Download resume/ });
  await expect(download).toBeVisible();
  const href = (await download.getAttribute("href"))!;
  expect((await page.request.get(href)).status()).toBe(200);

  // G4: the recruiter records the withdrawal; future deliveries stop, the share stays.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  expect((await outreach("declined")).ok()).toBeTruthy();
  await page.request.post("/api/v1/auth/logout");
  await page.request.post("/api/v1/auth/login", { data: { email: employerEmail, password: "Sup3r-Secret-Pass!", division: "it" } });
  await page.goto("/it/employer/dashboard");
  await expect(card).toBeVisible();
  await expect(card.getByText("Resume on request")).toBeVisible();
  await expect(card.getByRole("link", { name: /Download resume/ })).toHaveCount(0);
  expect((await page.request.get(href)).status()).toBe(404);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(card).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("favicon") && !e.includes("status of 422") && !e.includes("status of 404"))).toEqual([]); // deliberate refusals
});
