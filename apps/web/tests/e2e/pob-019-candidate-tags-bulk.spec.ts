import { expect, test, type Page } from "@playwright/test";

// pob-019 (DEC-SCOPE-437): a manager adds a candidate tag in the catalogue (T1); the seeded recruiter tags candidates on their pages (T2),
// finds them by the tag alone (T4) with the enriched cards (T5, AC1), shortlists the selection in one go with the Do Not Contact one skipped
// (T7/T8, AC2) and assigns that one a task (T9). A phone shows the bulk bar without sideways scroll.
const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("tags, enriched cards, bulk shortlist with a skip and a bulk task", async ({ page }) => {
  test.setTimeout(180_000);
  const tag = Date.now().toString(36);
  const tagName = `Hot ${tag}`;

  // T1: the manager adds the tag on the catalogue's new tab
  await signIn(page, "admin", MANAGER);
  await page.goto("/recruiter/manager/catalogue/candidate-tags");
  await page.getByLabel(/name \(required\)/).fill(tagName);
  await page.getByRole("button", { name: "Add candidate tag" }).click();
  await expect(page.getByRole("status").filter({ hasText: tagName })).toBeVisible();

  await signIn(page, "it", RECRUITER);
  const tagId = ((await (await page.request.get("/api/v1/recruiter/catalogue/candidate-tags?limit=100")).json()).items as { id: string; name: string }[])
    .find((t) => t.name === tagName)!.id;
  const sources = (await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json()).items as { id: string }[];
  const people: { id: string; name: string }[] = [];
  for (const first of ["Asha", "Ravi", "Meena"]) {
    const made = await page.request.post("/api/v1/recruiter/candidates", {
      data: { name: `POB19 ${first} ${tag}`, email: `pob19-${first.toLowerCase()}-${tag}@example.com`, location: "Pune", source_id: sources[0].id,
              experience_months: 30, lawful_basis: "provided_for_placement" },
    });
    expect(made.status(), await made.text()).toBe(201);
    people.push(await made.json());
  }
  const [asha, ravi, meena] = people;
  const dnc = await page.request.patch(`/api/v1/recruiter/candidates/${meena.id}`, { data: { status: "do_not_contact" } });
  expect(dnc.ok(), await dnc.text()).toBeTruthy();
  for (const p of [ravi, meena]) expect((await page.request.put(`/api/v1/recruiter/candidates/${p.id}/tags`, { data: { tag_ids: [tagId] } })).ok()).toBeTruthy();

  // T2: Asha's page -- add the tag from the Tags section
  await page.goto(`/recruiter/candidates/${asha.id}`);
  const tags = page.getByRole("region", { name: "Tags" });
  await expect(tags.getByText("No tags yet.")).toBeVisible();
  await tags.getByRole("button", { name: "Edit tags" }).click();
  await tags.getByRole("checkbox", { name: tagName }).check();
  await tags.getByRole("button", { name: "Save tags" }).click();
  await expect(tags.getByText("Tags saved.")).toBeVisible();
  await expect(tags.getByRole("list", { name: "Candidate tags" })).toHaveText(tagName);

  const company = (await (await page.request.post("/api/v1/recruiter/companies", { data: { name: `POB19 Co ${tag} Ltd` } })).json()).company;
  const r = (await (await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: company.id, title: `POB19 Dev ${tag}`, location: "Pune" } })).json()).requirement;
  if (r.status === "new") expect((await page.request.post(`/api/v1/recruiter/requirements/${r.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();

  // T4/T5 (AC1): the tag alone is a search; each card shows the five facts and the tags
  await page.goto(`/recruiter/find-candidates?tag=${tagId}`);
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();
  await expect(page.getByRole("button", { name: `Remove Candidate tags: ${tagName}` })).toBeVisible();
  const card = page.getByRole("listitem", { name: new RegExp(`^POB19 Ravi ${tag}`) });
  for (const fact of ["Owner", "Last contacted", "Active applications", "Prior submissions"]) await expect(card.getByText(fact, { exact: true })).toBeVisible();
  await expect(card.getByRole("list", { name: "Tags" })).toContainText(tagName);
  await expect(card.getByRole("list", { name: "Tags" })).toContainText("1–3 years");

  // T7/T8 (AC2): shortlist all three; Meena (Do Not Contact) is skipped with the reason and stays selected
  for (const p of people) await page.getByRole("checkbox", { name: `Select ${p.name}`, exact: true }).check();
  await expect(page.getByRole("button", { name: "Shortlist selected (3)" })).toBeDisabled();
  await page.getByRole("combobox", { name: "Shortlist into requirement" }).fill(`POB19 Dev ${tag}`);
  await page.getByRole("option", { name: new RegExp(`POB19 Dev ${tag}`) }).click();
  await page.getByRole("button", { name: "Shortlist selected (3)" }).click();
  await expect(page.getByText(`Shortlisted 2 candidates for POB19 Dev ${tag} — POB19 Co ${tag} Ltd.`)).toBeVisible();
  await expect(page.getByText(`${meena.name}: This candidate is marked Do Not Contact`)).toBeVisible();
  await expect(page.getByRole("checkbox", { name: `Select ${meena.name}`, exact: true })).toBeChecked();
  const listed = (await (await page.request.get(`/api/v1/recruiter/requirements/${r.id}/candidates`)).json()).items as { candidate: { id: string }; status: string }[];
  expect(listed.map((a) => a.status).sort()).toEqual(["shortlisted", "shortlisted"]);

  // rec-019's share still opens from the bulk bar
  await page.getByRole("button", { name: "Share selected (1)" }).click();
  const share = page.getByRole("form", { name: "Share 1 profile" });
  await expect(share).toBeVisible();
  await share.getByRole("button", { name: "Cancel" }).click();

  // a phone keeps the bulk bar inside the screen
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("group", { name: "Selected candidates" })).toBeVisible();
  expect(await noSideScroll(page)).toBeTruthy();
  await page.setViewportSize({ width: 1280, height: 900 });

  // T9: a task for the one still selected
  const me = (await (await page.request.get("/api/v1/auth/me")).json()) as { full_name: string };
  await page.getByRole("button", { name: "Assign task (1)" }).click();
  const form = page.getByRole("form", { name: "Assign a task to 1 candidate" });
  await form.getByLabel("Task type").selectOption("follow_up");
  await form.getByLabel("Title").fill("Ask about another role");
  const inAWeek = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + 7 * 86_400_000));
  await form.getByLabel("Due (IST)").fill(`${inAWeek}T10:00`); // hrc-016: within the next 12 months
  await form.getByRole("combobox", { name: "Assign to" }).fill(me.full_name);
  await page.getByRole("option", { name: new RegExp(me.full_name) }).first().click();
  await form.getByRole("button", { name: "Create 1 task" }).click();
  await expect(page.getByText("Created 1 task.")).toBeVisible();
  const tasks = (await (await page.request.get(`/api/v1/recruiter/candidates/${meena.id}/tasks`)).json()).items as { title: string }[];
  expect(tasks.map((t) => t.title)).toEqual(["Ask about another role"]);
});
