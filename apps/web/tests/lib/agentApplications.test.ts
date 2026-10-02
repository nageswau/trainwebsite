import { describe, expect, it } from "vitest";

import { canConfirmEnrollment, canWithdraw, deadlineText, GROUP_LABELS, nextStages, parseGroup, stageLabel } from "@/lib/agentApplications";
import { activityLabel } from "@/lib/agentStaff";

describe("canConfirmEnrollment (AGN-013 E6)", () => {
  it("allows offer, visa documentation and status tracking only", () => {
    const all = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled", "withdrawn", "University review"];
    expect(all.filter(canConfirmEnrollment)).toEqual(["offer", "visa_documentation", "status_tracking"]);
  });
});

describe("agent application rules (AGN-008)", () => {
  it("offers only later stages, never past status_tracking", () => {
    expect(nextStages("enquiry")).toEqual(["eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking"]);
    expect(nextStages("visa_documentation")).toEqual(["status_tracking"]);
    expect(nextStages("status_tracking")).toEqual([]);
    expect(nextStages("enrolled")).toEqual([]);
    expect(nextStages("withdrawn")).toEqual([]);
    expect(nextStages("university_review")).toEqual(["enquiry", ...nextStages("enquiry")]); // legacy value = before the first stage
  });

  it("withdraws anything but enrolled or already withdrawn", () => {
    expect(canWithdraw("offer")).toBe(true);
    expect(canWithdraw("enrolled")).toBe(false);
    expect(canWithdraw("withdrawn")).toBe(false);
  });

  it("parses the sidebar filter, falling back to all", () => {
    expect(parseGroup("offer")).toBe("offer");
    expect(parseGroup("rejected")).toBe("all");
    expect(parseGroup(null)).toBe("all");
    expect(GROUP_LABELS.offer).toBe("Offer received");
  });

  it("words deadlines in text, not colour", () => {
    expect(deadlineText(null, "2026-10-02")).toBeNull();
    expect(deadlineText({ kind: "offer", date: "2026-10-01" }, "2026-10-02")).toBe("Offer deadline 2026-10-01 (past)");
    expect(deadlineText({ kind: "application", date: "2026-10-02" }, "2026-10-02")).toBe("Application deadline 2026-10-02 (today)");
    expect(deadlineText({ kind: "application", date: "2026-10-03" }, "2026-10-02")).toBe("Application deadline 2026-10-03 (in 1 day)");
    expect(deadlineText({ kind: "application", date: "2026-10-30" }, "2026-10-02")).toBe("Application deadline 2026-10-30");
  });

  it("labels stages and the new activity actions", () => {
    expect(stageLabel("visa_documentation")).toBe("Visa documentation");
    expect(stageLabel("withdrawn")).toBe("Withdrawn");
    // QA8-11: a legacy value reads as a sentence-case label.
    expect(stageLabel("university_review")).toBe("University review");
    expect(activityLabel("overseas.application.update")).toBe("Edited an application");
    expect(activityLabel("overseas.application.advance")).toBe("Moved an application forward");
    expect(activityLabel("overseas.application.withdraw")).toBe("Withdrew an application");
  });
});
