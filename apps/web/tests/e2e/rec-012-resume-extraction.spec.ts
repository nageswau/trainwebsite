import { expect, test, type Page } from "@playwright/test";

// rec-012 (AC1-AC3, EX6): a recruiter uploads a resume, the review panel suggests the source sentence's five skills and the profile
// details, nothing is saved until "Save selected", and the saved skills appear on the Skills card as Resume / Claimed. HR has no review.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** A one-page PDF whose text layer holds `lines` (Helvetica), with a correct cross-reference table. */
function textPdf(lines: string[]): Buffer {
  const escape = (s: string) => s.replace(/[\\()]/g, (c) => `\\${c}`);
  const stream = `BT /F1 11 Tf 50 780 Td 14 TL ${lines.map((l) => `(${escape(l)}) '`).join(" ")} ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = objects.map((body, i) => {
    const at = pdf.length;
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
    return at;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

test("a recruiter reviews a resume's extracted details and saves the chosen ones; HR cannot review", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  await signIn(page, "placement@edusphere.local", "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral");
  const created = await page.request.post("/api/v1/recruiter/candidates", { data: { name: `Extract Test ${stamp}`, email: `extract${stamp}@example.com`, source_id: source.id } });
  expect(created.status()).toBe(201);
  const candidate = await created.json();

  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const resumeCard = page.getByRole("region", { name: "Resume" });
  await resumeCard.getByLabel("Upload resume").setInputFiles({
    name: "ravi.pdf", mimeType: "application/pdf",
    buffer: textPdf([
      "Ravi Kumar - Senior Java Developer", "Location: Pune", "B.Tech in Computer Science", "3 years of experience",
      "Developed enterprise applications using Java, Spring Boot, Hibernate and REST APIs with MySQL.",
    ]),
  });
  await resumeCard.getByRole("button", { name: "Upload", exact: true }).click();

  // AC1: the five skills of the source sentence, ticked at Intermediate; the profile details the candidate lacks are ticked too.
  const panel = page.getByRole("region", { name: /Review extracted details — version 1/ });
  const skills = panel.getByRole("group", { name: /Skills found/ });
  for (const name of ["Java", "Spring Boot", "Hibernate", "REST API", "MySQL"]) {
    await expect(skills.getByRole("checkbox", { name: new RegExp(`^${name} `) })).toBeChecked();
  }
  await expect(skills.getByText("found as “REST APIs”")).toBeVisible();
  const details = panel.getByRole("group", { name: "Profile details" });
  await expect(details.getByRole("checkbox", { name: /Qualification: B\.Tech/ })).toBeChecked();
  await expect(details.getByRole("checkbox", { name: /Total experience: 3 yr/ })).toBeChecked();
  await expect(details.getByRole("checkbox", { name: /Location: Pune/ })).toBeChecked();
  await expect(panel.getByText("Senior Java Developer")).toBeVisible();

  // AC2: nothing is on the profile before saving.
  const skillsCard = page.getByRole("region", { name: "Skills" });
  await expect(skillsCard.getByText("No skills added yet.")).toBeVisible();

  await skills.getByRole("checkbox", { name: /^MySQL / }).uncheck();
  await skills.getByRole("combobox", { name: "Level for Java" }).selectOption("advanced");
  await details.getByRole("checkbox", { name: /Location: Pune/ }).uncheck();
  await panel.getByRole("button", { name: "Save selected" }).click();
  await expect(resumeCard.getByText("Added 4 skills and updated total experience and qualification.")).toBeVisible();
  await expect(panel).toHaveCount(0);

  const java = skillsCard.getByRole("row", { name: /^Java Programming/ });
  await expect(java).toContainText("Advanced");
  await expect(java).toContainText("Resume");
  await expect(java).toContainText("Claimed");
  await expect(skillsCard.getByRole("row", { name: /Spring Boot/ })).toContainText("Intermediate");
  await expect(skillsCard.getByRole("row", { name: /MySQL/ })).toHaveCount(0);
  const profile = page.getByRole("region", { name: "Profile" });
  await expect(profile).toContainText("B.Tech");
  await expect(profile).toContainText("3 yr");

  // Reopening marks the saved skills as already on the profile.
  await resumeCard.getByRole("button", { name: "Review extracted details" }).click();
  await expect(skills.getByRole("checkbox", { name: /^Java / })).toBeDisabled();
  await expect(skills.getByRole("checkbox", { name: /^MySQL / })).toBeChecked();
  await panel.getByRole("button", { name: "Discard" }).click();
  await expect(panel).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  // EX10: HR reads the candidate but gets no review.
  await signIn(page, "hr@edusphere.local", "/it/hr/dashboard");
  await page.goto(`/recruiter/candidates/${candidate.id}`);
  await expect(page.getByRole("region", { name: "Resume" }).getByRole("link", { name: /Version 1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Review extracted details" })).toHaveCount(0);
});
