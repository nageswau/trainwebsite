import { describe, expect, it } from "vitest";
import { documentName, parseView, reviewDecisions, statusLabel, VIEW_LABELS, VIEWS } from "@/lib/agentDocuments";
import type { User } from "@/lib/types";

const agent = (role: "master" | "staff", canVerify = false) =>
  ({ role: "agent", agent_member_role: role, agent_permissions: { can_verify_documents: canVerify, can_view_reports: false } }) as unknown as User;

describe("agentDocuments (AGN-009)", () => {
  it("reads the sidebar view, Pending by default", () => {
    expect(VIEWS).toEqual(["pending", "uploaded", "additional"]);
    expect(parseView("uploaded")).toBe("uploaded");
    expect(parseView("additional")).toBe("additional");
    expect(parseView(null)).toBe("pending");
    expect(parseView("everything")).toBe("pending");
    expect(VIEW_LABELS.additional).toBe("Additional documents");
  });

  it("words a status, never the stored value", () => {
    expect(statusLabel("pending")).toBe("Pending review");
    expect(statusLabel("changes_required")).toBe("Changes required");
    expect(statusLabel("verified")).toBe("Verified");
    expect(statusLabel("some_legacy_value")).toBe("Some legacy value");
  });

  it("names an Other document by its label", () => {
    expect(documentName({ document_type: "Passport", document_label: null })).toBe("Passport");
    expect(documentName({ document_type: "Other", document_label: "Medical report" })).toBe("Medical report");
  });

  it("offers review decisions by the §6 matrix (DEC-SCOPE-044 P1/P6)", () => {
    expect(reviewDecisions(agent("master"))).toEqual(["verified", "rejected", "changes_required"]);
    expect(reviewDecisions(agent("staff", true))).toEqual(["verified"]);
    expect(reviewDecisions(agent("staff", false))).toEqual([]);
  });
});
