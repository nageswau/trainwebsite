import { expect, test, type Page } from "@playwright/test";

// rec-016 (AC1-AC3; DEC-SCOPE-157 M1-M8): the source's Java requirement. The placement manager makes test skills; the seeded recruiter
// adds Rahul (every skill), Priya (required only) and Arun (missing SQL), and a requirement with required + preferred skills, an
// experience range, a location and one skill outside the Skills Master. Rahul ranks first at 100%, Arun is not listed, Shortlist adds
// Rahul once (the Candidates section updates), a heavier Java weight re-ranks Priya, the manager reads without any write control, and
// the assigned BDM sees the requirement without the Matching section.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const BDM = "bdm.college@edusphere.local";

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), `${url} → ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test("matching: Rahul ranks first at 100%, shortlist once, weights re-rank, the manager reads only, phone width", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));
  const n = (name: string) => `${name} ${stamp}`;

  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  const categories = await (await page.request.get("/api/v1/recruiter/skill-categories?limit=100")).json();
  const category = categories.items.find((c: { name: string }) => c.name === "Programming").id;
  for (const s of ["MJava", "MSpring", "MSQL", "MMicro", "MAWS"]) await post(page, "/api/v1/recruiter/skills", { name: n(s), category_id: category });
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const candidate = async (name: string, fields: Record<string, unknown>, skills: string[]) => {
    const c = await post(page, "/api/v1/recruiter/candidates", { name: n(name), email: `match${name.toLowerCase()}${stamp}@example.com`, source_id: source, ...fields });
    for (const s of skills) await post(page, `/api/v1/recruiter/candidates/${c.id}/skills`, { skill: n(s), level: "advanced" });
  };
  await candidate("Rahul", { location: "Hyderabad", experience_months: 24, preferred_role: "Java Developer" }, ["MJava", "MSpring", "MSQL", "MMicro", "MAWS"]);
  await candidate("Priya", { location: "Pune", experience_months: 60 }, ["MJava", "MSpring", "MSQL"]);
  await candidate("Arun", { location: "Hyderabad", experience_months: 24 }, ["MJava", "MSpring"]);
  const bdms = await (await page.request.get("/api/v1/recruiter/companies/bdm-options?q=Vivek&limit=20")).json();
  const bdm = bdms.items.find((b: { full_name: string }) => b.full_name === "Vivek College BDM").id;
  const company = await post(page, "/api/v1/recruiter/companies", { name: `E2E Match ${stamp} Ltd`, assigned_bdm_user_id: bdm });
  const requirement = (await post(page, "/api/v1/recruiter/requirements", {
    company_id: company.company.id, title: n("Java Developer"), location: "Hyderabad", experience_min_months: 0, experience_max_months: 36,
    required_skills: [n("MJava"), n("MSpring"), n("MSQL"), n("Weblogic")], preferred_skills: [n("MMicro"), n("MAWS")],
  })).requirement;

  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const section = page.getByRole("region", { name: /^Matching candidates/ });
  await expect(section.getByRole("heading", { name: "Matching candidates (2)" })).toBeVisible();
  const rows = section.getByRole("list", { name: "Matching candidates" }).getByRole("listitem").filter({ has: page.getByRole("link", { name: /View profile/ }) });
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText(n("Rahul"));
  await expect(rows.nth(0)).toContainText("100% match");
  await expect(rows.nth(1)).toContainText(n("Priya"));
  await expect(rows.nth(1)).toContainText("60% match");
  await expect(section).not.toContainText(n("Arun"));
  await expect(section.getByText(`Not used for matching (not in the Skills Master): ${n("Weblogic")}`)).toBeVisible();
  await expect(rows.nth(1).getByRole("list", { name: `Score breakdown for ${n("Priya")}` })).toContainText("Location: 0 of 10");

  // AC3: Shortlist adds one application; the row then shows the status and the Candidates section lists it.
  await section.getByRole("button", { name: `Shortlist ${n("Rahul")}` }).click();
  await expect(section.getByText(`${n("Rahul")} shortlisted.`)).toBeVisible();
  await expect(rows.nth(0)).toContainText("Shortlisted");
  await expect(section.getByRole("button", { name: `Shortlist ${n("Rahul")}` })).toHaveCount(0);
  await expect(page.getByRole("region", { name: /^Candidates/ }).getByRole("heading", { name: "Candidates (1)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: /^Matching candidates/ }).getByRole("button", { name: `Shortlist ${n("Rahul")}` })).toHaveCount(0);

  // M1: Java 2 -> 10 makes Java 50 of the 80 skill points; Priya (Java, Spring, SQL; out of range; Pune) = 50 + 10 + 10 = 70.
  const matches = page.getByRole("region", { name: /^Matching candidates/ });
  await matches.getByRole("button", { name: "Adjust weights" }).click();
  await matches.getByLabel(`Weight of ${n("MJava")} (required)`).fill("10");
  await matches.getByRole("button", { name: "Save weights" }).click();
  await expect(page.getByText("Match weights saved.")).toBeVisible();
  await expect(matches.getByRole("list", { name: "Matching candidates" })).toContainText("70% match");

  // Phone width: the section never scrolls sideways.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(matches.getByRole("heading", { name: "Matching candidates (2)" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  await page.setViewportSize({ width: 1280, height: 900 });

  // M7: the manager reads the ranking with no Shortlist, Contact or weights.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const read = page.getByRole("region", { name: /^Matching candidates/ });
  await expect(read.getByRole("heading", { name: "Matching candidates (2)" })).toBeVisible();
  await expect(read.getByRole("button", { name: /^Shortlist/ })).toHaveCount(0);
  await expect(read.getByRole("button", { name: "Adjust weights" })).toHaveCount(0);
  await expect(read.getByRole("link", { name: /^Contact/ })).toHaveCount(0);

  // QA-01: the assigned BDM reads the requirement (R10) but not the candidate pool -- no Matching section, no refused call.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", BDM, "/bdm/my-day");
  await page.goto(`/recruiter/requirements/${requirement.id}`);
  await expect(page.getByRole("heading", { name: n("Java Developer") })).toBeVisible();
  await expect(page.getByRole("region", { name: /^Candidates/ })).toBeVisible();
  await expect(page.getByRole("region", { name: /^Matching candidates/ })).toHaveCount(0);

  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
