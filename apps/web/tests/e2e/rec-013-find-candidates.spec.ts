import { expect, test, type Page } from "@playwright/test";

// rec-013 (AC1-AC4; FS1-FS10): the placement manager makes test skills (Java with an alias and a related skill, AWS, Azure); the seeded
// recruiter adds three candidates, searches by the alias (related skills count), adds an OR group, narrows by a location facet (kept on
// refresh, undone by Back), shortlists into a requirement, and recovers from an unknown skill by its suggestion. HR searches read-only.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), `${url} → ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test("find candidates: alias + related, OR group, facet, refresh/back, shortlist, unknown skill; HR reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  // The manager's Skills Master: Java (alias J2EE, related Core Java), AWS, Azure -- unique to this run.
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  const categories = await (await page.request.get("/api/v1/recruiter/skill-categories?limit=100")).json();
  const category = categories.items.find((c: { name: string }) => c.name === "Programming").id;
  const skill = async (name: string) => post(page, "/api/v1/recruiter/skills", { name: `${name} ${stamp}`, category_id: category });
  const java = await skill("E2EJava");
  const core = await skill("E2ECore");
  await skill("E2EAWS");
  await skill("E2EAzure");
  await post(page, `/api/v1/recruiter/skills/${java.id}/aliases`, { alias: `E2EJ2EE ${stamp}` });
  await post(page, `/api/v1/recruiter/skills/${java.id}/related`, { skill_id: core.id });
  await page.request.post("/api/v1/auth/logout");

  // The recruiter's three candidates and one requirement.
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const candidate = async (name: string, fields: Record<string, unknown>, skills: string[]) => {
    const c = await post(page, "/api/v1/recruiter/candidates", { name: `${name} ${stamp}`, email: `find${name.toLowerCase()}${stamp}@example.com`, source_id: source, ...fields });
    for (const s of skills) await post(page, `/api/v1/recruiter/candidates/${c.id}/skills`, { skill: `${s} ${stamp}`, level: "advanced" });
    return c;
  };
  await candidate("Asha", { location: "Hyderabad", notice_days: 0, experience_months: 36, expected_salary: "800000", preferred_role: "Java Developer" }, ["E2EJava", "E2EAWS"]);
  await candidate("Bala", { location: "Pune", notice_days: 30, experience_months: 18 }, ["E2ECore", "E2EAzure"]);
  await candidate("Chitra", { location: "Hyderabad", notice_days: 60 }, ["E2EJava"]);
  const company = await post(page, "/api/v1/recruiter/companies", { name: `E2E Find ${stamp} Ltd` });
  const title = `Find Java ${stamp}`;
  const requirement = (await post(page, "/api/v1/recruiter/requirements", { company_id: company.company.id, title, location: "Hyderabad" })).requirement;

  // AC1: the alias finds Java's holders, and Core Java (related) counts too.
  await page.getByRole("link", { name: "Find Candidates" }).first().click();
  await page.waitForURL("**/recruiter/find-candidates");
  await expect(page.getByText("Add a skill or a resume search to search every candidate in the pool.")).toBeVisible();
  const all = page.getByRole("textbox", { name: "Must have all of these skills" });
  await all.fill(`E2EJ2EE ${stamp}`);
  await all.press("Enter");
  await page.getByRole("button", { name: "Search candidates" }).click();
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();
  await expect(page.getByText(`E2EJ2EE ${stamp} → E2EJava ${stamp}, E2ECore ${stamp}`)).toBeVisible();

  // AC3: Java AND (AWS OR Azure).
  await page.getByRole("button", { name: "+ Add an “at least one of” group" }).click();
  const group = page.getByRole("textbox", { name: "And at least one of these (group 1)" });
  for (const s of ["E2EAWS", "E2EAzure"]) {
    await group.fill(`${s} ${stamp}`);
    await group.press("Enter");
  }
  await page.getByRole("button", { name: "Search candidates" }).click();
  await expect(page.getByRole("heading", { name: "2 candidates found" })).toBeVisible();

  // AC4 + FS7: a location facet narrows; refresh keeps it; Back undoes it.
  const facets = page.getByRole("complementary", { name: "Refine results" });
  await expect(facets.getByRole("button", { name: /Hyderabad\s*1/ })).toBeVisible();
  await facets.getByRole("button", { name: /Hyderabad/ }).click();
  await expect(page.getByRole("heading", { name: "1 candidate found" })).toBeVisible();
  await expect(page).toHaveURL(/location=Hyderabad/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "1 candidate found" })).toBeVisible();
  const card = page.getByRole("listitem", { name: new RegExp(`Asha ${stamp}`) });
  await expect(card).toContainText("Java Developer | 3 yr");
  await expect(card).toContainText("Immediate");
  await expect(card).toContainText("₹8 LPA");
  await expect(card).toContainText("Referral");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "2 candidates found" })).toBeVisible();

  // FS9: shortlist into the requirement, through rec-017.
  await page.getByRole("combobox", { name: "Shortlist into requirement" }).fill(title);
  await page.getByRole("option", { name: new RegExp(title) }).click();
  const asha = page.getByRole("listitem", { name: new RegExp(`Asha ${stamp}`) });
  await asha.getByRole("button", { name: `Shortlist Asha ${stamp}` }).click();
  await expect(asha.getByText(new RegExp(`Shortlisted for ${title}`))).toBeVisible();
  await expect(asha.getByRole("button", { name: `Shortlist Asha ${stamp}` })).toBeDisabled();
  const onRequirement = await (await page.request.get(`/api/v1/recruiter/requirements/${requirement.id}/candidates`)).json();
  expect(onRequirement.items.map((a: { candidate: { name: string }; status: string }) => [a.candidate.name, a.status])).toEqual([[`Asha ${stamp}`, "shortlisted"]]);

  // FS3: an unknown skill names the suggestion, which swaps in.
  await page.goto(`/recruiter/find-candidates?all=${encodeURIComponent(`Java ${stamp}`)}`);
  await expect(page.locator("p[role=alert]")).toContainText(`No skill is called “Java ${stamp}”`);
  await page.getByRole("button", { name: `Use E2EJava ${stamp}` }).click();
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();

  // Mobile: no sideways scrolling.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // FS10: HR searches but has no Shortlist / Contact.
  await signIn(page, "it", "hr@edusphere.local", "/it/hr/dashboard");
  await page.goto(`/recruiter/find-candidates?all=${encodeURIComponent(`E2EJava ${stamp}`)}`);
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Shortlist/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^Contact/ })).toHaveCount(0);

  // The deliberate unknown-skill 422 is logged by the browser; nothing else may be.
  expect(consoleErrors.filter((e) => !e.includes("status of 422"))).toEqual([]);
  expect(failedCalls).toEqual([]);
});
