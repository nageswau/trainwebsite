import { describe, expect, it } from "vitest";

import { fieldErrors, historyUrl, isBackward, orgActionUrl, type Pipeline, pipelineQuery, stageChanged } from "@/lib/bdmPipeline";

const pipeline = (stage: string): Pipeline => ({
  stage, stage_label: stage, lost: null, agent_status: null,
  steps: ["prospect", "contacted", "meeting", "proposal"].map((key) => ({ key, label: key, kind: "manual", state: "upcoming" })),
});

describe("bdm-004 pipeline helpers", () => {
  it("builds the organization action and history URLs", () => {
    expect(orgActionUrl("o1", "stage")).toBe("/api/v1/bdm/organizations/o1/stage");
    expect(historyUrl("o1", 20)).toBe("/api/v1/bdm/organizations/o1/stage-history?limit=20&offset=20");
  });

  it("knows a backward move from the catalogue order", () => {
    expect(isBackward(pipeline("meeting"), "contacted")).toBe(true);
    expect(isBackward(pipeline("meeting"), "proposal")).toBe(false);
  });

  it("reads the stale-move 409 and the field 422s", () => {
    expect(stageChanged({ code: "stage_changed", current_stage: "contacted", message: "x" })).toBe("contacted");
    expect(stageChanged("Restore this organization first")).toBeNull();
    expect(fieldErrors([{ loc: ["body", "note"], msg: "Value error, Note contains invalid characters" }, { loc: ["body", "to_stage"], msg: "Choose a stage" }]))
      .toEqual({ note: "Note contains invalid characters", to_stage: "Choose a stage" });
    expect(fieldErrors("plain")).toEqual({});
  });

  it("drops empty filters from the query", () => {
    expect(pipelineQuery({ assigned: "me", stage: undefined, offset: 0 })).toBe("assigned=me&limit=50&offset=0");
    expect(pipelineQuery({ bdm_type: "school", stage: "lost", offset: 50 })).toBe("bdm_type=school&stage=lost&limit=50&offset=50");
  });
});
