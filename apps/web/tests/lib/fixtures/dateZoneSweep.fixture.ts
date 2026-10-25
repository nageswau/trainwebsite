// Fixture for tests/lib/dateZoneSweep.test.ts (not app code): each function is a shape the date-zone guard must judge correctly.
// multiLine, variableFlag, storedDate and optionsWithoutZone are unzoned and must be flagged; the rest are fine and must not be.
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

export function zonedLocaleIsFine(v: string, timeZone: string) {
  return [new Date(v).toLocaleString("en-GB", { timeZone: "UTC" }), new Date(v).toLocaleDateString("en-GB", { timeZone })];
}

export function optionsWithoutZone(v: string) {
  return new Date(v).toLocaleDateString("en-GB", { day: "numeric" });
}
