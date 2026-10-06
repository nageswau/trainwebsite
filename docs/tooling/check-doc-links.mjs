// Fails when a Markdown link or image under the documentation folders points at a missing file.
// Usage (repo root): node docs/tooling/check-doc-links.mjs [root]
//   no root    -> the Agent CRM set (docs/user-manual, docs/admin-manual, docs/role-guides, docs/*.md)
//   root given -> the same layout under that folder, e.g. docs/school-crm; a folder without that layout
//                 (e.g. docs/demo) is checked as a whole
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const base = process.argv[2] ?? "docs";
const dirs = ["user-manual", "admin-manual", "role-guides"].map((d) => join(base, d));
const files = ["faq.md", "troubleshooting.md", "screenshot-index.md"].map((f) => join(base, f)).filter(existsSync);
const walk = (d) =>
  existsSync(d)
    ? readdirSync(d).filter((f) => !f.startsWith(".")).flatMap((f) => {
        const p = join(d, f);
        return statSync(p).isDirectory() ? walk(p) : p.endsWith(".md") ? [p] : [];
      })
    : [];

let bad = 0;
const standard = dirs.some(existsSync) || files.length > 0;
for (const f of standard ? [...dirs.flatMap(walk), ...files] : walk(base)) {
  for (const m of readFileSync(f, "utf8").matchAll(/\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
    const target = m[1];
    if (/^(https?:|mailto:)/.test(target)) continue;
    if (!existsSync(resolve(dirname(f), target))) {
      console.log(`${f}: missing ${target}`);
      bad++;
    }
  }
}
console.log(bad ? `${bad} broken link(s)` : "All links OK");
process.exit(bad ? 1 : 0);
