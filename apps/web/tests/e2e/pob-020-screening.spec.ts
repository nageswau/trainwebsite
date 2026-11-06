import { type Browser, expect, type Page, test } from "@playwright/test";

// pob-020 (DEC-SCOPE-412): AC1 a five-question form from the template, AC2 a knock-out after the Team Lead's approval, AC3 kept sessions, AC4 the
// comparison. The seeded recruiter builds and runs the form; the seeded placement manager approves and reads, and cannot run a session.
const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const PERMIT = "Do you hold a valid work permit?";

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function addCandidate(page: Page, requirementId: string, name: string, mobile: string) {
  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(mobile);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.locator("#cand-lawful_basis").selectOption("provided_for_placement");
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: page.url().split("/").pop() } });
  expect(added.status()).toBe(201);
}

async function asManager(browser: Browser, requirementId: string, act: (page: Page) => Promise<void>) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(`/recruiter/requirements/${requirementId}`);
  await act(page);
  await context.close();
}

test("AC1-AC4: template form, Team Lead approval, knock-out, kept sessions and comparison", async ({ page, browser }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const names = [`E2E Priya ${stamp}`, `E2E Arun ${stamp}`];
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("screening") && response.status() >= 500 && failedCalls.push(`${response.status()} ${response.url()}`));
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Screen Form Co ${stamp}` } });
  const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: (await company.json()).company.id, title: `Screen form ${stamp}`, location: "Pune" } });
  const requirementId = (await created.json()).requirement.id as string;
  await addCandidate(page, requirementId, names[0], `8${String(stamp).slice(-9)}`);
  await addCandidate(page, requirementId, names[1], `7${String(stamp).slice(-9)}`);

  // AC1: five questions from the default template
  await page.goto(`/recruiter/requirements/${requirementId}`);
  const section = page.getByRole("region", { name: "Screening form", exact: true });
  await section.getByRole("button", { name: "Show screening form" }).click();
  await expect(section.getByText(/no screening form yet/i)).toBeVisible();
  await section.getByRole("button", { name: "Create form" }).click();
  await expect(section.getByText("Screening form created.")).toBeVisible();
  await expect(section.locator("ol > li")).toHaveCount(5);

  // A knock-out needs a Team Lead: the recruiter is not offered the approval
  await section.getByRole("button", { name: "Edit questions" }).click();
  await section.getByLabel("Question 1", { exact: true }).fill(PERMIT);
  await section.getByLabel("Answer format for question 1").selectOption("yes_no");
  await section.getByLabel("Knock-out (question 1)").check();
  await section.getByRole("button", { name: "Save new version" }).click();
  await expect(section.getByText("Saved as version 2.")).toBeVisible();
  await expect(section.getByText("Knock-outs awaiting Team Lead approval")).toBeVisible();
  await expect(section.getByRole("button", { name: "Approve knock-outs" })).toHaveCount(0);

  await asManager(browser, requirementId, async (manager) => {
    const managed = manager.getByRole("region", { name: "Screening form", exact: true });
    await managed.getByRole("button", { name: "Show screening form" }).click();
    await managed.getByRole("button", { name: "Approve knock-outs" }).click();
    await expect(managed.getByText("Knock-outs approved.")).toBeVisible();
  });

  // AC2: a "No" saves as Reject whatever was chosen, unless overridden with a reason. AC3: every session stays.
  await page.reload();
  const candidates = page.getByRole("region", { name: /^Candidates/ });
  const open = async (name: string) => {
    await candidates.getByRole("button", { name: `Screening of ${name}` }).click();
    await candidates.getByRole("button", { name: `Record a session for ${name}` }).click();
  };
  const runner = candidates.getByRole("form", { name: "Record a screening session" });
  await open(names[0]);
  await runner.getByLabel(new RegExp(`^${PERMIT.replace("?", "\\?")}`)).selectOption("no");
  await expect(runner.getByText(/will be saved as Reject/)).toBeVisible();
  await runner.getByLabel("Recommendation").selectOption("pass");
  await runner.getByRole("button", { name: "Save session" }).click();
  await expect(candidates.getByText("Session recorded.")).toBeVisible();
  const history = candidates.getByRole("list", { name: `Screening sessions of ${names[0]}` });
  await expect(history.locator("> li").first()).toContainText("Reject");
  await expect(history.locator("> li").first()).toContainText("Knock-out failed");

  await candidates.getByRole("button", { name: `Record a session for ${names[0]}` }).click();
  await runner.getByLabel(new RegExp(`^${PERMIT.replace("?", "\\?")}`)).selectOption("no");
  await runner.getByLabel("Override the knock-out").check();
  await runner.getByLabel(/^How well does the candidate communicate/).selectOption("4");
  await runner.getByLabel("Recommendation").selectOption("pass");
  await runner.getByRole("button", { name: "Save session" }).click();
  await expect(runner.getByText("Give a reason for overriding the knock-out.")).toBeVisible();
  await runner.getByLabel("Reason for the override").fill("Renewal confirmed by email");
  await runner.getByRole("button", { name: "Save session" }).click();
  await expect(history.locator("> li")).toHaveCount(2);
  await expect(history.locator("> li").first()).toContainText("Knock-out overridden");
  await expect(history.locator("> li").first()).toContainText("Pass");

  // S9: the status did not move
  await candidates.getByRole("button", { name: `Screening of ${names[0]}` }).click();
  await open(names[1]);
  await runner.getByLabel(new RegExp(`^${PERMIT.replace("?", "\\?")}`)).selectOption("yes");
  await runner.getByLabel(/^How well does the candidate communicate/).selectOption("2");
  await runner.getByLabel("Recommendation").selectOption("hold");
  await runner.getByRole("button", { name: "Save session" }).click();
  await expect(candidates.getByRole("list", { name: `Screening sessions of ${names[1]}` }).locator("> li")).toHaveCount(1);
  const board = await (await page.request.get(`/api/v1/recruiter/requirements/${requirementId}/candidates`)).json();
  expect(board.items.map((i: { status: string }) => i.status)).toEqual(["sourced", "sourced"]);

  // AC4: side by side, best first, as the manager too; a manager has no runner
  await asManager(browser, requirementId, async (manager) => {
    const managed = manager.getByRole("region", { name: "Screening form", exact: true });
    await managed.getByRole("button", { name: "Show screening form" }).click();
    await managed.getByRole("button", { name: "Compare candidates" }).click();
    const table = managed.getByRole("table", { name: /Screening comparison/ });
    await expect(table.locator("tbody tr").first()).toContainText(names[0]);
    await expect(table.getByRole("row", { name: new RegExp(names[0]) })).toContainText("4 / 5 (80%)");
    await expect(table.getByRole("row", { name: new RegExp(names[1]) })).toContainText("2 / 5 (40%)");
    // QA-02: on a phone every score and the question list stay on screen
    await manager.setViewportSize({ width: 375, height: 740 });
    const score = await table.getByText("4 / 5 (80%)").boundingBox();
    expect((score?.x ?? 0) + (score?.width ?? 999)).toBeLessThanOrEqual(375);
    const legend = await managed.getByRole("list", { name: "Questions compared" }).boundingBox();
    expect((legend?.x ?? 0) + (legend?.width ?? 999)).toBeLessThanOrEqual(375);
    await manager.setViewportSize({ width: 1280, height: 800 });
    const list = manager.getByRole("region", { name: /^Candidates/ });
    await list.getByRole("button", { name: `Screening of ${names[0]}` }).click();
    await expect(list.getByRole("list", { name: `Screening sessions of ${names[0]}` }).locator("> li")).toHaveCount(2);
    await expect(list.getByRole("button", { name: /Record a session/ })).toHaveCount(0);
  });
  expect(failedCalls).toEqual([]);
});

test("the question bank adds, finds and archives a question; templates list the default", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/screening-bank");
  const text = `E2E bank question ${Date.now()}?`;
  await expect(page.getByRole("list", { name: "Templates" }).locator("strong", { hasText: "Standard 5-category screening" })).toBeVisible();
  await page.getByRole("button", { name: "Add question" }).click();
  await page.getByLabel("Question text").fill(text);
  await page.getByRole("button", { name: "Save question" }).click();
  await expect(page.getByRole("button", { name: "Add question" })).toBeVisible();
  await page.getByLabel("Search questions").fill(text);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const list = page.getByRole("list", { name: "Questions" });
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await list.getByRole("button", { name: /^Archive/ }).click();
  await expect(page.getByText("No questions match.")).toBeVisible();
});
