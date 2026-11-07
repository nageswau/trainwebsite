import { expect, test, type Page } from "@playwright/test";

// pob-023 (DEC-SCOPE-408): the seeded recruiter adds a shared LinkedIn template (a draft no one can use yet) and edits it (v2); the
// seeded placement manager approves it; the recruiter then copies it for a company contact -- Copy appears only after the preview, and
// the copy is logged. A personal calling script shows its steps. The library has no sideways scroll on a phone.
const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

test("a recruiter's draft is approved by the Team Lead, then copied and logged from a company", async ({ page, context }) => {
  test.setTimeout(150_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const stamp = Date.now();
  const name = `E2E LinkedIn ${stamp}`;
  const script = `E2E Call ${stamp}`;

  // AC1: a recruiter's shared template is a draft
  await signIn(page, "it", RECRUITER);
  await page.goto("/recruiter/templates");
  const create = page.getByRole("form", { name: "Add a template" });
  await create.getByLabel("Channel (required)").selectOption("linkedin");
  await create.getByLabel("Template name (required)").fill(name);
  await create.getByLabel("Purpose", { exact: true }).fill("First note to an HR lead");
  await create.getByLabel("Message (required)").fill("Hi {name}, I'm {recruiter} -- we place great people at {company}.");
  await create.getByRole("button", { name: "Add template" }).click();
  await expect(create.getByText(`Created ${name} as a draft.`)).toBeVisible();
  const usable = await (await page.request.get("/api/v1/recruiter/templates?usable=true&channel=linkedin&limit=100")).json();
  expect(usable.items.map((t: { name: string }) => t.name)).not.toContain(name);

  // AC5: a personal calling script with steps
  await create.getByLabel("Channel (required)").selectOption("call");
  await create.getByLabel("Template name (required)").fill(script);
  await create.getByLabel("Opening (required)").fill("Hello {name}, this is {recruiter}.");
  await create.getByLabel(/^Steps/).fill("Ask about open roles\nAgree a follow-up date");
  await create.getByRole("radio", { name: /Personal/ }).check();
  await create.getByRole("button", { name: "Add template" }).click();
  await expect(create.getByText(`Created ${script}.`)).toBeVisible();

  // AC2: an edit is a new version
  await page.goto(`/recruiter/templates?q=${encodeURIComponent(name)}`);
  await page.getByRole("button", { name: `Edit ${name}`, exact: true }).click();
  await page.locator("tbody form").getByLabel("Purpose", { exact: true }).fill("First note, revised");
  await page.getByRole("button", { name: "Save (new version)" }).click();
  await expect(page.getByText(`Saved ${name}.`)).toBeVisible();
  await page.getByRole("button", { name: `Versions of ${name}` }).click();
  await expect(page.getByRole("list", { name: `Versions of ${name}` }).locator("li")).toHaveCount(2);
  await expect(page.getByRole("button", { name: `Approve ${name}` })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // AC1: the Team Lead approves it
  await signIn(page, "admin", MANAGER);
  await page.goto(`/recruiter/manager/templates?status=draft&q=${encodeURIComponent(name)}`);
  await page.getByRole("button", { name: `Approve ${name}` }).click();
  await expect(page.getByText(`Approved ${name}. The team can use it now.`)).toBeVisible();

  // AC4: copy mode on a company page, after the preview, logged
  await signIn(page, "it", RECRUITER);
  const created = await page.request.post("/api/v1/recruiter/companies", {
    data: { name: `E2E Pob023 ${stamp} Pvt`, contact: { name: "Meera Iyer", mobile: "+91 98450 12345", is_primary: true } },
  });
  expect(created.status(), await created.text()).toBe(201);
  await page.goto(`/recruiter/companies/${(await created.json()).company.id}`);
  const box = page.locator("section").filter({ has: page.getByRole("heading", { name: "Messages", exact: true }) });
  await box.getByRole("button", { name: "LinkedIn message" }).click();
  const linkedin = box.getByRole("group", { name: "LinkedIn message" });
  await expect(linkedin.getByRole("button", { name: "Copy to clipboard" })).toHaveCount(0);
  await linkedin.getByLabel("Template").selectOption({ label: name });
  await expect(linkedin.getByLabel(/^Message \(preview/)).toHaveValue(/^Hi Meera Iyer, I'm Kiran Placement/);
  await linkedin.getByRole("button", { name: "Copy to clipboard" }).click();
  await expect(box.getByText("LinkedIn message for Meera Iyer copied and logged.")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("Hi Meera Iyer");

  // AC5: the calling script's steps
  await box.getByRole("button", { name: "Calling script" }).click();
  const call = box.getByRole("group", { name: "calling script" });
  await call.getByLabel("Template").selectOption({ label: `${script} (personal)` });
  await expect(call.getByRole("listitem")).toHaveText(["Ask about open roles", "Agree a follow-up date"]);
});
