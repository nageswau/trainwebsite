import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { beforeAll, describe, expect, it } from "vitest";

// Date sweep (after QA-023-07): every date shown to a user must name its zone, or the server (UTC) and the browser disagree -- React's
// hydration error #418 on hydrated components, and server UTC shown to users everywhere else. The rules:
//   - calendar dates (YYYY-MM-DD)      -> formatCalendarDate(v)
//   - school portal timestamps (D10)   -> formatDate(v, withTime, SCHOOL_TIME_ZONE) / formatSchoolDateTime(v, label)
//   - other timestamps (viewer's zone) -> <LocalTime value=... />
// So any formatDate call with fewer than three arguments, and any toLocale*String called on a Date, is a finding. Numbers
// (amount.toLocaleString()) are fine. The check reads the TypeScript syntax tree and types (not the source text), so line breaks,
// a variable time flag, or a Date kept in a variable cannot hide a call (review finding).
const ROOT = join(__dirname, "..", "..");
const DIRS = ["app", "components", "lib"].map((d) => join(ROOT, d));
const ALLOWED = new Map<string, string>([
  ["lib/formatDate.ts", "defines the helpers"],
  // An <option> can hold only text, and this list is fetched in the browser after mount, so the browser's zone is already the viewer's.
  ["components/WorkflowPanel.tsx", "client-fetched <option> text"],
]);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.(tsx?|jsx?)$/.test(name) ? [path] : [];
  });
}

type Finding = { file: string; line: number; rule: string };
const LOCALE_METHODS = new Set(["toLocaleString", "toLocaleDateString", "toLocaleTimeString"]);
const FIXTURE = join(__dirname, "fixtures", "dateZoneSweep.fixture.ts");
const SOURCES = [...DIRS.flatMap(files), FIXTURE];

// One program over every scanned file, with the app's own compiler options (so the "@/..." paths and lib types resolve).
let program: ts.Program;
beforeAll(() => {
  const configPath = ts.findConfigFile(ROOT, ts.sys.fileExists, "tsconfig.json")!;
  const { options } = ts.parseJsonConfigFileContent(ts.readConfigFile(configPath, ts.sys.readFile).config, ts.sys, ROOT);
  program = ts.createProgram(SOURCES, { ...options, noEmit: true });
}, 120_000);

function scan(paths: string[]): Finding[] {
  const checker = program.getTypeChecker();
  return paths.flatMap((path) => {
    const rel = relative(ROOT, path).replaceAll("\\", "/");
    if (ALLOWED.has(rel)) return [];
    const source = program.getSourceFile(path)!;
    const found: Finding[] = [];
    const add = (node: ts.Node, rule: string) => found.push({ file: rel, line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1, rule });
    const visit = (node: ts.Node): void => {
      if (ts.isCallExpression(node)) {
        const callee = node.expression;
        if (ts.isIdentifier(callee) && callee.text === "formatDate" && node.arguments.length < 3) add(node, "formatDate without a zone");
        if (ts.isPropertyAccessExpression(callee) && LOCALE_METHODS.has(callee.name.text)) {
          const receiver = checker.getTypeAtLocation(callee.expression);
          if (receiver.getSymbol()?.getName() === "Date") add(node, `Date#${callee.name.text}`);
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(source);
    return found;
  });
}

describe("dates are always formatted with a zone", () => {
  // Review finding (date sweep): the guard must see a multi-line call, a variable time flag and a Date held in a variable -- and must
  // still pass a number's toLocaleString() and a zoned call. Lines refer to tests/lib/fixtures/dateZoneSweep.fixture.ts.
  it("flags exactly the unzoned shapes in the fixture", () => {
    expect(scan([FIXTURE]).map((f) => f.line)).toEqual([6, 13, 18]);
  });

  it("finds no unzoned date formatting in app/, components/ or lib/", () => {
    expect(scan(DIRS.flatMap(files)).map((f) => `${f.file}:${f.line} ${f.rule}`)).toEqual([]);
  });
});
