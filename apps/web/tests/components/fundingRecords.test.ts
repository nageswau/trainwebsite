import { describe, expect, it } from "vitest";
import { FUNDING_STATUSES, isFinal, nextStatuses, stageText, STATUS_LABEL, SUPPORT_TYPE_LABEL } from "@/lib/fundingRecords";

// ENH-020 (spec §3.2): the browser offers only the moves the API accepts -- the same table as schemas.FUNDING_STATUS_NEXT.
describe("fundingRecords", () => {
  it("offers one step forward or Closed from every open stage, nothing from a final one", () => {
    expect(nextStatuses("required")).toEqual(["counselling", "closed"]);
    expect(nextStatuses("counselling")).toEqual(["documents", "closed"]);
    expect(nextStatuses("documents")).toEqual(["application", "closed"]);
    expect(nextStatuses("application")).toEqual(["approved", "closed"]);
    expect(nextStatuses("approved")).toEqual(["completed", "closed"]);
    expect(nextStatuses("completed")).toEqual([]);
    expect(nextStatuses("closed")).toEqual([]);
  });

  it("knows which stages are final", () => {
    expect(FUNDING_STATUSES.filter(isFinal)).toEqual(["completed", "closed"]);
  });

  it("describes a stage in words, with its place in the six source stages", () => {
    expect(stageText("required")).toBe("Stage 1 of 6 · Required");
    expect(stageText("documents")).toBe("Stage 3 of 6 · Documents");
    expect(stageText("completed")).toBe("Stage 6 of 6 · Completed");
    expect(stageText("closed")).toBe("Closed");
  });

  it("labels every type and stage", () => {
    expect(SUPPORT_TYPE_LABEL.education_loan).toBe("Education loan");
    expect(SUPPORT_TYPE_LABEL.funding_guidance).toBe("Funding guidance");
    expect(FUNDING_STATUSES.map((s) => STATUS_LABEL[s])).toEqual(["Required", "Counselling", "Documents", "Application", "Approved", "Completed", "Closed"]);
  });
});
