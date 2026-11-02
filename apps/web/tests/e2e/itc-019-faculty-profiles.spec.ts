import { deflateSync } from "node:zlib";

import { expect, test, type Browser, type Page } from "@playwright/test";

// itc-019 (DEC-SCOPE-346): the seeded trainer (Meera Iyer) fills in her faculty profile with a photo, keeps her email hidden, and the
// seeded student (Arjun Rao, actively enrolled in her batch) sees it on the Course page -- without the hidden details. The IT Admin opens
// the same profile from the Trainers page. The profile is reset at the end so reruns start from the same state.
test.describe.configure({ timeout: 120_000 });

const TRAINER = "trainer@edusphere.local";
const STUDENT = "student.it@edusphere.local";

async function signIn(browser: Browser, email: string, landing: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}**`);
  return page;
}

/** A plain grey 200 × 200 PNG (the photo must be at least 120 px a side). */
function png(side = 200): Buffer {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf: Buffer) => {
    let c = 0xffffffff;
    for (const byte of buf) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (kind: string, body: Buffer) => {
    const head = Buffer.alloc(4);
    head.writeUInt32BE(body.length);
    const tail = Buffer.alloc(4);
    tail.writeUInt32BE(crc(Buffer.concat([Buffer.from(kind), body])));
    return Buffer.concat([head, Buffer.from(kind), body, tail]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(side, 0);
  ihdr.writeUInt32BE(side, 4);
  ihdr.set([8, 0, 0, 0, 0], 8);
  const rows = Buffer.concat(Array.from({ length: side }, () => Buffer.concat([Buffer.from([0]), Buffer.alloc(side, 0x99)])));
  return Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "binary"), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

test("a trainer's profile reaches their student, minus the hidden details", async ({ browser }) => {
  const hours = `Mon–Fri 6–7 pm (e2e ${Date.now() % 100000})`;
  const errors: string[] = [];
  const trainer = await signIn(browser, TRAINER, "/it/trainer");
  trainer.on("pageerror", (e) => errors.push(e.message));

  await trainer.getByRole("navigation").getByRole("link", { name: "Profile", exact: true }).click();
  await expect(trainer.getByRole("heading", { name: "Faculty Profile", level: 2 })).toBeVisible();
  await trainer.getByLabel("Designation").fill("Senior Python Trainer");
  await trainer.getByRole("textbox", { name: "Expertise" }).fill("Python, Django, python");
  await trainer.getByLabel("Office hours", { exact: true }).fill(hours);
  await trainer.getByLabel("Show my email to students").setChecked(false);
  await trainer.getByLabel("How students should contact you").selectOption("in_app");
  await trainer.getByRole("button", { name: "Save profile" }).click();
  await expect(trainer.getByText("Profile saved.")).toBeVisible();
  await expect(trainer.getByRole("textbox", { name: "Expertise" })).toHaveValue("Python, Django");

  await trainer.getByLabel(/PNG, JPEG or WebP/).setInputFiles({ name: "me.png", mimeType: "image/png", buffer: png() });
  await trainer.getByRole("button", { name: "Upload photo" }).click();
  await expect(trainer.getByText("Photo saved.")).toBeVisible();
  await expect(trainer.getByRole("img", { name: /Current photo of/ })).toBeVisible();

  const student = await signIn(browser, STUDENT, "/it/student");
  student.on("pageerror", (e) => errors.push(e.message));
  await student.goto("/it/student/course");
  const card = student.locator("section", { has: student.getByRole("heading", { name: "My faculty", level: 3 }) });
  await expect(card.getByRole("heading", { name: "Meera Iyer" }).first()).toBeVisible();
  await expect(card.getByText(hours).first()).toBeVisible();
  await expect(card.getByText("Senior Python Trainer").first()).toBeVisible();
  await expect(card.getByRole("img", { name: "Photo of Meera Iyer" }).first()).toBeVisible();
  await expect(card.getByText(TRAINER)).toHaveCount(0); // AC1: the hidden email is not on the page
  const faculty = (await (await student.request.get("/api/v1/it/student/faculty")).json()) as { items: { faculty: Record<string, unknown> | null }[] };
  for (const item of faculty.items) {
    if (item.faculty) expect(Object.keys(item.faculty)).not.toContain("email");
  }

  const admin = await signIn(browser, "itadmin@edusphere.local", "/it/admin");
  admin.on("pageerror", (e) => errors.push(e.message));
  await admin.goto("/it/admin/trainers");
  await expect(admin.getByRole("heading", { name: "Faculty profiles", level: 3 })).toBeVisible();
  const picker = admin.getByLabel("Trainer", { exact: true });
  await picker.selectOption({ label: "Meera Iyer" });
  await expect(admin.getByLabel("Office hours", { exact: true })).toHaveValue(hours);

  // reset for reruns
  await trainer.request.delete("/api/v1/it/trainer/profile/photo");
  expect(errors).toEqual([]);
});
