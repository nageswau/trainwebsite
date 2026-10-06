// Builds the documentation PDFs: pandoc (Markdown -> one HTML per book, images embedded) + Playwright's
// Chromium (HTML -> A4 PDF with page numbers). Usage (repo root):
//   node docs/tooling/build-pdfs.mjs          -> Agent CRM, output docs/pdf/*.pdf
//   node docs/tooling/build-pdfs.mjs school   -> School CRM, output docs/school-crm/pdf/*.pdf
// Intermediate HTML goes to <output>/.build/ (git-ignored by <output>/.gitignore).
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const SCHOOL = process.argv[2] === "school";
const ROOT = path.resolve(SCHOOL ? "docs/school-crm" : "docs");
const OUT = path.join(ROOT, "pdf");
const BUILD = path.join(OUT, ".build");
mkdirSync(BUILD, { recursive: true });
writeFileSync(path.join(OUT, ".gitignore"), ".build/\n");

const md = (dir) => readdirSync(path.join(ROOT, dir)).filter((f) => /^[a-z0-9]+-\d{3}-.*\.md$/.test(f)).sort().map((f) => `${dir}/${f}`);
const PREFIX = SCHOOL ? "EduSphere School CRM — " : "EduSphere Agent CRM — ";
const UM = ["account-access", "dashboard", "students", "universities", "applications", "documents", "tasks", "notifications", "commissions", "reports", "team", "staff-performance"];
const SCHOOL_UM = ["account-access", "dashboards", "students", "team", "transfers", "activities", "academic-team", "portfolio",
  "career-counselor", "psychometric-team", "student-360", "reports", "entitlements", "notifications", "parent"];
const SCHOOL_ROLES = ["school-coordinator", "principal", "teacher", "parent", "academic-team", "career-counselor", "psychometric-team",
  "overseas-admin-schools", "super-admin-schools"];
const SCHOOL_BOOKS = () => [
  { file: "EduSphere-School-CRM-User-Manual", title: "EduSphere School CRM — User Manual", subtitle: "For School Coordinators, Principals, Teachers, Parents, Academic Team, Career Counselors and Psychometric Team", pages: SCHOOL_UM.flatMap((d) => md(`user-manual/${d}`)) },
  { file: "EduSphere-School-CRM-Admin-Manual", title: "EduSphere School CRM — Administrator Manual", subtitle: "For Overseas Admins and Super Admins", pages: ["admin-manual/README.md", ...md("admin-manual")] },
  { file: "EduSphere-School-CRM-Role-Guides", title: "EduSphere School CRM — Role Quick-Start Guides", subtitle: "Nine roles, from School Coordinator to Super Admin", pages: SCHOOL_ROLES.map((r) => `role-guides/${r}.md`) },
  { file: "EduSphere-School-CRM-FAQ-and-Troubleshooting", title: "EduSphere School CRM — FAQ and Troubleshooting", subtitle: "Answers and fixes based on verified behaviour", pages: ["faq.md", "troubleshooting.md"] },
];
const AGENT_BOOKS = () => [
  { file: "EduSphere-Agent-CRM-User-Manual", title: "EduSphere Agent CRM — User Manual", subtitle: "For Agency Masters and Agency Staff", pages: UM.flatMap((d) => md(`user-manual/${d}`)) },
  { file: "EduSphere-Agent-CRM-Admin-Manual", title: "EduSphere Agent CRM — Administrator Manual", subtitle: "For Overseas Admins and Super Admins", pages: ["admin-manual/README.md", ...md("admin-manual")] },
  { file: "EduSphere-Agent-CRM-Role-Guides", title: "EduSphere Agent CRM — Role Quick-Start Guides", subtitle: "Agency Master · Agency Staff · Overseas Admin · Super Admin", pages: ["role-guides/agency-master.md", "role-guides/agency-staff.md", "role-guides/overseas-admin-agencies.md", "role-guides/super-admin-agencies.md"] },
  { file: "EduSphere-Agent-CRM-FAQ-and-Troubleshooting", title: "EduSphere Agent CRM — FAQ and Troubleshooting", subtitle: "Answers and fixes based on verified behaviour", pages: ["faq.md", "troubleshooting.md"] },
];
const BOOKS = SCHOOL ? SCHOOL_BOOKS() : AGENT_BOOKS();
const bookOf = (rel) => BOOKS.find((b) => b.pages.includes(rel));
const anchor = (rel) => "p-" + rel.replace(/\.md$/, "").replace(/[^a-z0-9]+/gi, "-").toLowerCase();

const CSS = `
@page { size: A4; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1d2433; max-width: none; margin: 0; padding: 0; }
header#title-block-header { text-align: center; padding: 70mm 0 0; page-break-after: always; }
header#title-block-header .title { font-size: 26pt; margin-bottom: 6mm; }
header#title-block-header .subtitle { font-size: 13pt; color: #4a5568; }
header#title-block-header .date { margin-top: 30mm; color: #4a5568; }
nav#TOC { page-break-after: always; }
nav#TOC h2 { font-size: 16pt; color: #0b2a55; }
nav#TOC > ul { list-style: none; padding-left: 0; columns: 1; }
nav#TOC li { margin: 1.5mm 0; }
nav#TOC a { color: #1d2433; text-decoration: none; }
h1 { font-size: 18pt; color: #0b2a55; border-bottom: 2px solid #0b5cc4; padding-bottom: 2mm; page-break-before: always; margin-top: 0; }
h2 { font-size: 13pt; color: #0b2a55; margin-top: 6mm; page-break-after: avoid; }
h3 { font-size: 11pt; margin-top: 4mm; page-break-after: avoid; }
blockquote { color: #4a5568; font-size: 9pt; border-left: 3px solid #cbd5e0; margin: 0 0 3mm; padding: 1mm 3mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9pt; page-break-inside: auto; }
th, td { border: 1px solid #cbd5e0; padding: 1.2mm 2mm; vertical-align: top; text-align: left; }
th { background: #eef2f7; }
tr { page-break-inside: avoid; }
img { max-width: 100%; max-height: 225mm; width: auto; height: auto; object-fit: contain; border: 1px solid #cbd5e0; margin: 2mm 0; page-break-inside: avoid; display: block; }
figure { margin: 2mm 0 4mm; page-break-inside: avoid; }
figcaption { font-size: 8.5pt; color: #4a5568; }
code { font-size: 9pt; background: #f1f4f8; padding: 0 1mm; }
a { color: #0b5cc4; }
.xref { color: #4a5568; font-style: italic; }
`;

function transform(rel, book) {
  const dir = path.posix.dirname(rel);
  let text = readFileSync(path.join(ROOT, rel), "utf8");
  // Images: make paths relative to docs/ (pandoc runs with cwd = docs).
  text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => `![${alt}](${path.posix.normalize(path.posix.join(dir, src))})`);
  // Links to other .md pages: in-book anchors, otherwise plain text.
  text = text.replace(/(?<!!)\[([^\]]+)\]\(([^)\s]+\.md)(#[^)]*)?\)/g, (_, label, target) => {
    const t = path.posix.normalize(path.posix.join(dir, target));
    if (book.pages.includes(t)) return `[${label}](#${anchor(t)})`;
    const other = bookOf(t);
    return other ? `${label} [(see the ${other.title.replace(PREFIX, "")})]{.xref}` : label;
  });
  // Pandoc needs a blank line before a list that directly follows a paragraph line (GitHub does not).
  text = text.replace(/^([^\n|>#\-*\d\s][^\n]*)\n((?:[-*]|\d+\.) )/gm, "$1\n\n$2");
  // First H1 gets the page anchor.
  return text.replace(/^# (.+)$/m, (_, h) => `# ${h} {#${anchor(rel)}}`);
}

const require = createRequire(path.resolve("apps/web/package.json"));
const { chromium } = require("@playwright/test");
const browser = await chromium.launch();
writeFileSync(path.join(BUILD, "print.css"), CSS);
const date = new Date().toISOString().slice(0, 10);

for (const book of BOOKS) {
  const missing = book.pages.filter((p) => !existsSync(path.join(ROOT, p)));
  if (missing.length) throw new Error(`Missing pages: ${missing.join(", ")}`);
  const combined = book.pages.map((p) => transform(p, book)).join("\n\n");
  const mdFile = path.join(BUILD, `${book.file}.md`);
  const htmlFile = path.join(BUILD, `${book.file}.html`);
  writeFileSync(mdFile, combined);
  execFileSync("pandoc", [mdFile, "--standalone", "--embed-resources",
    "--resource-path", ROOT, "--css", path.join(BUILD, "print.css"), "--toc", "--toc-depth=1", "--metadata", "toc-title=Contents",
    "--metadata", `title=${book.title}`, "--metadata", `subtitle=${book.subtitle}`, "--metadata", `date=Verified ${date}`,
    "--metadata", "lang=en", "-o", htmlFile], { cwd: ROOT, stdio: ["ignore", "inherit", "inherit"] });
  const page = await browser.newPage();
  await page.goto("file:///" + htmlFile.replace(/\\/g, "/"));
  const pdfFile = path.join(OUT, `${book.file}.pdf`);
  await page.pdf({
    path: pdfFile, format: "A4", printBackground: true,
    margin: { top: "16mm", bottom: "16mm", left: "14mm", right: "14mm" },
    displayHeaderFooter: true,
    headerTemplate: `<div style="font-size:7px;width:100%;padding:0 14mm;color:#718096">${book.title}</div>`,
    footerTemplate: `<div style="font-size:7px;width:100%;text-align:center;color:#718096"><span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
  });
  await page.close();
  const kb = Math.round(readFileSync(pdfFile).length / 1024);
  console.log(`${book.file}.pdf  ${book.pages.length} pages of content  ${kb} KB`);
}
await browser.close();
