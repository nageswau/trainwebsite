import { describe, expect, it } from "vitest";

import { STAGES, isClosed, needsReason, personTargets, stageLabel } from "@/lib/leadStages";

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
