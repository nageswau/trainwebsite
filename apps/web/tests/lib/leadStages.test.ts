import { describe, expect, it } from "vitest";

import { STAGES, counselorTargets, isClosed, needsReason, personTargets, stageLabel } from "@/lib/leadStages";

describe("leadStages (tel-004)", () => {
  it("lists 11 open stages and 5 closed outcomes with source labels", () => {
    expect(STAGES).toHaveLength(16);
    expect(stageLabel("first_call_pending")).toBe("First Call Pending");
    expect(stageLabel("application_enrollment")).toBe("Application/Enrollment");
    expect(stageLabel("legacy_text")).toBe("legacy_text");
    expect(isClosed("no_response")).toBe(true);
    expect(isClosed("follow_up")).toBe(false);
  });

  it("offers only manual stages and closed outcomes on an open lead, never a system stage", () => {
    const targets = personTargets("contacted", true);
    expect(targets).toEqual(["qualified", "interested", "follow_up", "not_interested", "not_eligible", "wrong_number", "no_response", "lost"]);
    expect(personTargets("qualified", false)).not.toContain("qualified");
    for (const system of ["new", "assigned", "first_call_pending", "contacted", "counselling_scheduled", "counselling_completed", "application_enrollment", "converted"]) {
      expect(targets).not.toContain(system);
    }
  });

  it("stops manual moves at the counselor and freezes a converted lead", () => {
    expect(personTargets("application_enrollment", true)).toEqual(["not_interested", "not_eligible", "wrong_number", "no_response", "lost"]);
    expect(personTargets("converted", true)).toEqual([]);
  });

  it("lets only a manager or admin reopen a closed lead, to Follow-up", () => {
    expect(personTargets("lost", true)).toEqual(["follow_up"]);
    expect(personTargets("lost", false)).toEqual([]);
  });

  it("requires a reason to close or reopen", () => {
    expect(needsReason("contacted", "lost")).toBe(true);
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
