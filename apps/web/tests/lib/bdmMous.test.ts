import { describe, expect, it } from "vitest";

import { BDM_MANAGER_NAV, BDM_NAV } from "@/lib/navigation";
import { mouConflict, MOU_STATUSES, mouDocumentUrl, mouHistoryUrl, mousQuery, orgMouUrl, SETTABLE_MOU_STATUSES } from "@/lib/bdmMous";

const SOURCE = ["Prospect", "Discussion Started", "Proposal Sent", "Under Negotiation", "Draft Shared", "Signed", "Active", "Expired", "Rejected"];

describe("bdm-005 MoU library (AC5)", () => {
  it("lists the source statuses exactly, in source order", () => {
    expect(MOU_STATUSES.map((s) => s.label)).toEqual(SOURCE);
  });

  it("never offers Expired as a choice (M2)", () => {
    expect(SETTABLE_MOU_STATUSES.map((s) => s.key)).toEqual(["prospect", "discussion_started", "proposal_sent", "under_negotiation", "draft_shared", "signed", "active", "rejected"]);
  });

  it("builds the URLs", () => {
    expect(orgMouUrl("o1")).toBe("/api/v1/bdm/organizations/o1/mou");
    expect(mouDocumentUrl("m1")).toBe("/api/v1/bdm/mous/m1/document");
    expect(mouHistoryUrl("m1", 20)).toBe("/api/v1/bdm/mous/m1/history?limit=20&offset=20");
    expect(mousQuery({ status: "expired", offset: 50 })).toBe("status=expired&limit=50&offset=50");
    expect(mousQuery({ organization: "o1", current: false })).toBe("organization=o1&current=false&limit=50&offset=0");
  });

  it("reads the MoU 409 bodies", () => {
    expect(mouConflict({ code: "mou_status_changed", message: "This MoU moved to Signed meanwhile", current_status: "signed" })).toBe("This MoU moved to Signed meanwhile.");
    expect(mouConflict({ code: "mou_expired", message: "This MoU has expired. Start a renewal." })).toBe("This MoU has expired. Start a renewal.");
    expect(mouConflict({ code: "organization_lost", message: "This organization is marked lost. Revive it first." })).toBe("This organization is marked lost. Revive it first.");
    expect(mouConflict({ code: "mou_changed", message: "This MoU was changed meanwhile" })).toBe("This MoU was changed meanwhile. Check it and try again.");
    expect(mouConflict("Restore this organization first")).toBeNull();
  });

  it("adds MoUs after Pipeline in both BDM navs", () => {
    const after = (nav: { label: string }[]) => nav[nav.findIndex((x) => x.label === "Pipeline") + 1].label;
    expect(after(BDM_NAV)).toBe("MoUs");
    expect(after(BDM_MANAGER_NAV)).toBe("MoUs");
  });
});
