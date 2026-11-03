import { describe, expect, it } from "vitest";

import { STAGES } from "@/lib/leadStages";
import { catalogueFrom, type StatusEntry } from "@/lib/statusLabels";

// itc-005 (DEC-SCOPE-362): the IT catalogue relabels and reorders IT lead stages, keeps overseas on the defaults, and lists a turned-off
// stage for filters while marking it off for the pickers (AC2).
const entry = (code: string, label: string, sort_order: number, enabled = true): StatusEntry =>
  ({ code, label, default_label: label, sort_order, enabled, can_disable: true });

describe("catalogueFrom", () => {
  const catalogue = catalogueFrom([entry("new", "New Lead", 10), entry("interested", "Course Interested", 15, false), entry("assigned", "Assigned", 20)]);

  it("uses the IT words for IT leads and the defaults for overseas leads", () => {
    expect(catalogue.label("interested", "it")).toBe("Course Interested");
    expect(catalogue.label("interested")).toBe("Course Interested");
    expect(catalogue.label("interested", "overseas")).toBe("Interested");
    expect(catalogue.label("qualified", "it")).toBe("Qualified"); // not in the catalogue: the default
  });

  it("orders the filter options as configured and keeps a turned-off stage there", () => {
    expect(catalogue.stages.map(([code]) => code)).toEqual(["new", "interested", "assigned"]);
    expect([...catalogue.off]).toEqual(["interested"]);
  });

  it("falls back to the defaults without a catalogue", () => {
    const defaults = catalogueFrom(null);
    expect(defaults.stages).toBe(STAGES);
    expect(defaults.label("interested", "it")).toBe("Interested");
    expect(defaults.off.size).toBe(0);
  });
});
