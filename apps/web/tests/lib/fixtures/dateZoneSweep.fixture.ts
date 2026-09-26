// Fixture for tests/lib/dateZoneSweep.test.ts (not app code): each function is a shape the date-zone guard must judge correctly.
// The first three are unzoned and must be flagged; the last two are fine and must not be.
import { formatDate } from "@/lib/formatDate";

export function multiLine(v: string) {
  return formatDate(
    v,
    true,
  );
}

export function variableFlag(v: string, withTime: boolean) {
  return formatDate(v, withTime);
}

export function storedDate(v: string) {
  const d = new Date(v);
  return d.toLocaleString();
}

export function numberIsFine(n: number) {
  return n.toLocaleString();
}

export function zonedIsFine(v: string) {
  return formatDate(v, true, "Asia/Kolkata");
}
