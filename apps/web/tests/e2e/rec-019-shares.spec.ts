import { expect, test, type Page } from "@playwright/test";

// rec-019 (AC1-AC4; DEC-SCOPE-158 S1-S14): a self-registered employer's company is assigned to the seeded recruiter, who adds two
// candidates (one with a resume) to a requirement. From the Candidates board the recruiter shares both on the Portal (both move to
// Profile Shared), is warned on a repeat and shares again by Email; the email (Mailpit) names them without their phone or email and its
// resume link downloads the file. The employer sees the profiles under "Shared with you" and answers Interested, which the recruiter then
// sees. Phone width keeps the board usable. MAILPIT_URL defaults to the rec019 stack's Mailpit.

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const MAILPIT = process.env.MAILPIT_URL ?? "http://host.docker.internal:8219";
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

test("share: portal + repeat + email from the board, the employer answers, phone width", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const recruiterId = (await (await page.request.get("/api/v1/auth/me")).json()).id;
  await page.request.post("/api/v1/auth/logout");

  const employerEmail = `rec019-${stamp}@example.local`;
  const registered = await post(page, "/api/v1/employer/register", {
    email: employerEmail, password: "Sup3r-Secret-Pass!", full_name: "Share Employer", company_name: `E2E Share ${stamp}`, company_website: "https://example.com",
  });
  const companyId = registered.company.id;
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await post(page, `/api/v1/recruiter/companies/${companyId}/assign`, { recruiter_user_id: recruiterId });
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const contactEmail = `hr${stamp}@example.com`;
  await post(page, `/api/v1/recruiter/companies/${companyId}/contacts`, { name: "Meera Iyer", mobile: "98450 12345", email: contactEmail });
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const rahul = await post(page, "/api/v1/recruiter/candidates", {
    name: `Rahul ${stamp}`, email: `rahul${stamp}@example.com`, mobile: `9${String(stamp).slice(-9)}`, source_id: source, qualification: "B.Tech", experience_months: 26,
  });
  const priya = await post(page, "/api/v1/recruiter/candidates", { name: `Priya ${stamp}`, email: `priya${stamp}@example.com`, source_id: source });
  const upload = await page.request.put(`/api/v1/recruiter/candidates/${rahul.id}/resume`, { multipart: { file: { name: "cv.pdf", mimeType: "application/pdf", buffer: PDF } } });
  expect(upload.ok()).toBeTruthy();
  const requirement = (await post(page, "/api/v1/recruiter/requirements", { company_id: companyId, title: `Java Developer ${stamp}`, location: "Pune" })).requirement;
  for (const c of [rahul, priya]) await post(page, `/api/v1/recruiter/requirements/${requirement.id}/candidates`, { candidate_id: c.id, status: "shortlisted" });

  // AC4 + S8: share both on the Portal from the board; both move to Profile Shared.
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const board = page.getByRole("region", { name: /^Candidates/ });
  await board.getByRole("checkbox", { name: `Select Rahul ${stamp} to share` }).check();
  await board.getByRole("checkbox", { name: `Select Priya ${stamp} to share` }).check();
  await board.getByRole("button", { name: "Share selected (2)" }).click();
  const dialog = board.getByRole("form", { name: "Share 2 profiles" });
  await dialog.getByLabel(/^Portal/).check();
  await dialog.getByRole("button", { name: "Share 2 profiles" }).click();
  await expect(board.getByText(`Shared 2 profiles for Java Developer ${stamp} by Portal with Meera Iyer.`)).toBeVisible();
  await board.getByRole("button", { name: "Close" }).click();
  await expect(board.getByRole("listitem").filter({ hasText: `Rahul ${stamp}` }).getByText("Profile Shared", { exact: true })).toBeVisible();
  const shares = page.getByRole("region", { name: /^Shared profiles/ });
  await expect(shares.getByText("Portal to Meera Iyer · 2 profiles")).toBeVisible();

  // S5: a repeat is warned, then sent by Email (AC1-AC3 through Mailpit).
  await board.getByRole("checkbox", { name: `Select Rahul ${stamp} to share` }).check();
  await board.getByRole("button", { name: "Share selected (1)" }).click();
  await board.getByRole("button", { name: "Share 1 profile" }).click();
  await expect(board.getByRole("alert")).toContainText("already shared");
  await board.getByRole("button", { name: "Share again" }).click();
  await expect(board.getByText(/Shared 1 profile for .* by Email with Meera Iyer\. The email is queued\./)).toBeVisible();
  await board.getByRole("button", { name: "Close" }).click();
  await expect(shares.getByRole("heading", { name: "Shared profiles (2)" })).toBeVisible();

  let mail: { Text: string } | null = null;
  for (let i = 0; i < 30 && !mail; i++) {
    const found = await (await page.request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${contactEmail}`)}`)).json();
    if (found.messages?.length) mail = await (await page.request.get(`${MAILPIT}/api/v1/message/${found.messages[0].ID}`)).json();
    else await page.waitForTimeout(1000);
  }
  expect(mail, "the share email reached Mailpit").not.toBeNull();
  expect(mail!.Text).toContain(`Rahul ${stamp} (${rahul.candidate_code})`);
  expect(mail!.Text).not.toContain(rahul.email);
  expect(mail!.Text).not.toContain(String(stamp).slice(-9));
  const link = mail!.Text.match(/https?:\/\/\S+\/api\/v1\/public\/shared-resume\/\S+/)![0];
  const resume = await page.request.get(link.replace(/^https?:\/\/[^/]+/, ""));
  expect(resume.status()).toBe(200);
  expect(Buffer.from(await resume.body()).subarray(0, 4).toString()).toBe("%PDF");

  // S8/S9: the employer sees only the summary and answers.
  await page.request.post("/api/v1/auth/logout");
  await page.request.post("/api/v1/auth/login", { data: { email: employerEmail, password: "Sup3r-Secret-Pass!", division: "it" } });
  await page.goto("/it/employer/dashboard");
  const portal = page.getByRole("region", { name: /^Shared with you/ });
  await expect(portal.getByRole("heading", { name: "Shared with you (2)" })).toBeVisible();
  const card = portal.getByRole("listitem").filter({ hasText: `Rahul ${stamp}` });
  await expect(card).toContainText("B.Tech");
  await expect(card).not.toContainText(rahul.email);
  await card.getByLabel("Your response").selectOption("interested");
  await card.getByRole("button", { name: /Save response/ }).click();
  await expect(portal.getByText(`Response saved for Rahul ${stamp}.`)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  await expect(page.getByRole("region", { name: /^Shared profiles/ }).getByText(/Response by Share Employer/)).toBeVisible();

  // Phone width: no sideways scroll on the requirement page with the dialog open.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("region", { name: /^Candidates/ }).getByRole("checkbox", { name: `Select Priya ${stamp} to share` }).check();
  await page.getByRole("button", { name: "Share selected (1)" }).click();
  await expect(page.getByRole("form", { name: "Share 1 profile" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();

  expect(failedCalls).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
