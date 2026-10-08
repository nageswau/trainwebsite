import { describe, expect, it } from "vitest";

import { boardHref, boardQuery, isBackward, lostConflict, stageHistoryUrl, type UniversityPipeline } from "@/lib/partnershipPipeline";

const stages = [
  { key: "target_university", label: "Target University", column: "target" },
  { key: "interested", label: "Interested", column: "interested" },
  { key: "proposal_sent", label: "Proposal Sent", column: "proposal_sent" },
];
const p = { stage: "interested", stages } as UniversityPipeline;

describe("upc-007 partnershipPipeline lib", () => {
  it("knows a backward move (PS4)", () => {
    expect(isBackward(p, "target_university")).toBe(true);
    expect(isBackward(p, "proposal_sent")).toBe(false);
  });

  it("reads only the university Lost conflicts", () => {
    expect(lostConflict({ code: "university_lost", message: "This university is marked lost. Reopen it first." })).toBe("This university is marked lost. Reopen it first.");
    expect(lostConflict({ code: "university_not_lost", message: "Not lost." })).toBe("Not lost.");
    expect(lostConflict({ code: "stage_changed", message: "x" })).toBeNull();
    expect(lostConflict("Reactivate this university first")).toBeNull();
  });

  it("builds the board query and the page links (filters in the URL, PS11)", () => {
    expect(boardQuery({ mine: true })).toBe("manager=me&limit=50&offset=0");
    expect(boardQuery({ mine: false, column: "lost", offset: 50 })).toBe("column=lost&limit=50&offset=50");
    expect(boardHref({ all: false })).toBe("/partnership/pipeline");
    expect(boardHref({ all: true, column: "negotiation", offset: 100 })).toBe("/partnership/pipeline?scope=all&column=negotiation&offset=100");
  });

  it("pages the stage history", () => {
    expect(stageHistoryUrl("u1", 20)).toBe("/api/v1/partnership/universities/u1/stage-history?limit=20&offset=20");
  });
});
