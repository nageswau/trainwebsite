import { describe, expect, it } from "vitest";

import { STAGES, assignedToCounselor, counselorTargets, isClosed, needsReason, personTargets, stageLabel } from "@/lib/leadStages";

describe("leadStages (itc-004, DEC-SCOPE-338)", () => {
  it("adds the open Nurture stage, a telecaller target that needs a reason (N2, N3)", () => {
    expect(stageLabel("nurture")).toBe("Nurture");
    expect(isClosed("nurture")).toBe(false);
    expect(STAGES.map(([key]) => key)).toContain("nurture");
    expect(personTargets("interested", false)).toContain("nurture");
    expect(personTargets("application_enrollment", true)).not.toContain("nurture");
    expect(personTargets("converted", true)).toEqual([]);
    expect(counselorTargets("qualified")).not.toContain("nurture");
    expect(needsReason("interested", "nurture")).toBe(true);
  });

  it("re-activates a Nurture lead through the manual stages, without a reason (N4)", () => {
    expect(personTargets("nurture", false)).toEqual(["qualified", "interested", "follow_up", "not_interested", "not_eligible", "wrong_number", "no_response", "lost", "duplicate"]);
    expect(counselorTargets("nurture")).toContain("follow_up");
    expect(needsReason("nurture", "follow_up")).toBe(false);
  });

  it("derives Assigned to Counselor from an open lead with a counselor (N1)", () => {
    const counselor = { id: "c1", full_name: "Kiran" };
    expect(assignedToCounselor({ status: "interested", counselor })).toBe(true);
    expect(assignedToCounselor({ status: "nurture", counselor })).toBe(true);
    expect(assignedToCounselor({ status: "interested", counselor: null })).toBe(false);
    expect(assignedToCounselor({ status: "lost", counselor })).toBe(false);
    expect(assignedToCounselor({ status: "converted", counselor })).toBe(false);
  });
});

describe("leadStages (tel-004)", () => {
  it("lists 11 open stages and 6 closed outcomes with source labels (ccrm-006: Duplicate, Wrong Number shown as Invalid Contact)", () => {
    expect(STAGES).toHaveLength(18); // itc-004: + Nurture
    expect(stageLabel("wrong_number")).toBe("Invalid Contact");
    expect(isClosed("duplicate")).toBe(true);
    expect(stageLabel("first_call_pending")).toBe("First Call Pending");
    expect(stageLabel("application_enrollment")).toBe("Application/Enrollment");
    expect(stageLabel("legacy_text")).toBe("legacy_text");
    expect(isClosed("no_response")).toBe(true);
    expect(isClosed("follow_up")).toBe(false);
  });

  it("offers only manual stages and closed outcomes on an open lead, never a system stage", () => {
    const targets = personTargets("contacted", true);
    expect(targets).toEqual(["qualified", "interested", "follow_up", "nurture", "not_interested", "not_eligible", "wrong_number", "no_response", "lost", "duplicate"]);
    expect(personTargets("qualified", false)).not.toContain("qualified");
    for (const system of ["new", "assigned", "first_call_pending", "contacted", "counselling_scheduled", "counselling_completed", "application_enrollment", "converted"]) {
      expect(targets).not.toContain(system);
    }
  });

  it("stops manual moves at the counselor and freezes a converted lead", () => {
    expect(personTargets("application_enrollment", true)).toEqual(["not_interested", "not_eligible", "wrong_number", "no_response", "lost", "duplicate"]);
    expect(personTargets("converted", true)).toEqual([]);
  });

  it("lets only a manager or admin reopen a closed lead, to Follow-up", () => {
    expect(personTargets("lost", true)).toEqual(["follow_up"]);
    expect(personTargets("lost", false)).toEqual([]);
  });

  it("requires a reason to close or reopen", () => {
    expect(needsReason("contacted", "no_response")).toBe(true);
    // ccrm-006 D5: Lost / Not Interested / Duplicate carry a structured reason instead
    for (const structured of ["lost", "not_interested", "duplicate"]) expect(needsReason("contacted", structured)).toBe(false);
    expect(needsReason("lost", "follow_up")).toBe(true);
    expect(needsReason("contacted", "qualified")).toBe(false);
  });
});

describe("counselorTargets (ccrm-003 A1, CC8)", () => {
  it("offers the CC8 open stages and closed outcomes, never the telecaller's or a system stage", () => {
    expect(counselorTargets("follow_up")).toEqual(["qualified", "counselling_scheduled", "counselling_completed", "not_interested", "not_eligible", "lost"]);
    expect(counselorTargets("contacted")).toContain("follow_up");
    for (const never of ["interested", "wrong_number", "no_response", "application_enrollment", "converted"]) {
      expect(counselorTargets("follow_up")).not.toContain(never);
    }
  });

  it("only closes a linked lead, freezes a converted one and never reopens", () => {
    expect(counselorTargets("application_enrollment")).toEqual(["not_interested", "not_eligible", "lost"]);
    expect(counselorTargets("converted")).toEqual([]);
    expect(counselorTargets("lost")).toEqual([]);
  });
});
